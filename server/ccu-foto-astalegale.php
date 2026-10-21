<?php
/*
 * CCU – Foto ufficiali Astalegale per le aste della provincia di Terni senza foto vera
 * Per ogni asta TR pubblicata che ha solo il segnaposto o la mappa:
 *   1. cerca il lotto nel feed RSS ufficiale Astalegale della provincia di Terni
 *      (confronto: comune + numero lotto + offerta minima/prezzo)
 *   2. scarica le foto dalla scheda ufficiale (max 6), le salva in webp
 *   3. toglie segnaposto/mappa. Non modifica nessun altro dato dell'annuncio.
 *
 * Uso:
 *   php ccu-foto-astalegale.php --prova          -> mostra cosa farebbe, NON scrive nulla
 *   php ccu-foto-astalegale.php                  -> esegue
 *   php ccu-foto-astalegale.php --id=4690        -> solo un annuncio
 */
require __DIR__ . '/includes/bootstrap.php';
$db = db(); $R = ROOT_PATH;

$prova  = in_array('--prova', $argv, true);
$soloId = 0;
foreach ($argv as $a) if (preg_match('/^--id=(\d+)$/', $a, $m)) $soloId = (int)$m[1];

$PROVINCE = ['tr' => 'umbria'];
$MAX_FOTO = 6;

function al_get(string $u): string
{
    $c = stream_context_create(['http' => ['header' => "User-Agent: Mozilla/5.0 (CercocasaUmbria)\r\n", 'timeout' => 30]]);
    return (string)@file_get_contents($u, false, $c);
}
function al_norm(string $s): string
{
    $s = mb_strtolower(trim($s));
    $s = (string)@iconv('UTF-8', 'ASCII//TRANSLIT', $s);
    return preg_replace('/[^a-z0-9]+/', ' ', $s);
}
function al_prezzi(string $t): array
{
    preg_match_all('/(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?)\s*(?:€|euro)|€\s*(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?)/iu', $t, $m, PREG_SET_ORDER);
    $out = [];
    foreach ($m as $x) {
        $v = $x[1] !== '' ? $x[1] : ($x[2] ?? '');
        if ($v !== '') $out[] = (float)str_replace(',', '.', str_replace('.', '', $v));
    }
    return $out;
}

/* 1. Leggo i feed RSS ufficiali */
$feed = [];
foreach ($PROVINCE as $prov => $reg) {
    $xml = al_get("https://www.asteimmobili.it/Immobili/Rss?province=$prov&regioni=$reg");
    if ($xml === '' || !($x = @simplexml_load_string($xml))) { echo "Feed $prov non leggibile\n"; continue; }
    foreach ($x->channel->item as $it) {
        $title = html_entity_decode(strip_tags((string)$it->title), ENT_QUOTES, 'UTF-8');
        $desc  = html_entity_decode(strip_tags((string)$it->description), ENT_QUOTES, 'UTF-8');
        $guid  = trim((string)$it->guid);
        if (!preg_match('/^B\d+$/', $guid) && preg_match('/(B\d{5,})/', (string)$it->link, $g)) $guid = $g[1];
        if (!$guid) continue;
        $feed[] = [
            'id'    => $guid,
            'lotto' => preg_match('/Lott?o?\s*(?:n\.?\s*)?(\w+)/iu', $title, $l) ? strtolower($l[1]) : '',
            'testo' => al_norm("$title $desc"),
            'prezzi'=> al_prezzi("$title $desc"),
        ];
    }
}
echo count($feed) . " lotti nel feed Astalegale\n";
if (!$feed) exit;

/* 2. Aste senza foto vera */
$sql = "SELECT p.id,p.code,p.city,p.price,p.minimum_bid,p.details_json
        FROM properties p
        WHERE p.operation='asta' AND p.status='pubblicato' AND p.province='TR'
          AND EXISTS (SELECT 1 FROM property_photos f WHERE f.property_id=p.id AND (f.path LIKE '%segnaposto%' OR f.path LIKE '%mappa-posizione%'))
          AND NOT EXISTS (SELECT 1 FROM property_photos f WHERE f.property_id=p.id AND f.path NOT LIKE '%segnaposto%' AND f.path NOT LIKE '%mappa-posizione%')";
if ($soloId) $sql .= " AND p.id=" . $soloId;
$rows = $db->query($sql)->fetchAll(PDO::FETCH_ASSOC);
echo count($rows) . " aste senza foto vera\n";

$insFoto = $db->prepare("INSERT INTO property_photos(property_id,path,alt_text,sort_order,watermark_status,watermark_version,watermarked_at) VALUES (?,?,?,?,'completata',2,NOW())");
$delSeg  = $db->prepare("DELETE FROM property_photos WHERE property_id=? AND (path LIKE '%segnaposto%' OR path LIKE '%mappa-posizione%')");
$fatte = 0;

foreach ($rows as $r) {
    $id = (int)$r['id'];
    $js = json_decode((string)$r['details_json'], true) ?: [];
    $lotto = strtolower((string)($js['lot'] ?? ''));
    if ($lotto === '' && preg_match('/-(\w+)$/', (string)$r['code'], $m) && substr_count((string)$r['code'], '-') >= 4) $lotto = strtolower($m[1]);
    $citta  = al_norm((string)$r['city']);
    $prezzi = array_filter([(float)$r['minimum_bid'], (float)$r['price']]);

    /* 3. Cerco il lotto: comune + lotto + prezzo */
    $match = null;
    foreach ($feed as $f) {
        if ($citta === '' || !str_contains(' ' . $f['testo'] . ' ', ' ' . $citta . ' ')) continue;
        if ($lotto !== '' && $f['lotto'] !== '' && $f['lotto'] !== $lotto) continue;
        $prezzoOk = false;
        foreach ($prezzi as $p) foreach ($f['prezzi'] as $q) if (abs($p - $q) < 1) $prezzoOk = true;
        if (!$prezzoOk) continue;
        if ($match) { $match = 'doppio'; break; }
        $match = $f;
    }
    if (!$match)            { echo "#$id {$r['city']}: nessun lotto Astalegale corrispondente\n"; continue; }
    if ($match === 'doppio') { echo "#$id {$r['city']}: più lotti corrispondenti, salto per sicurezza\n"; continue; }

    /* 4. Foto dalla scheda ufficiale */
    $h = al_get("https://www.astalegale.net/Aste/Detail/{$match['id']}"); sleep(1);
    preg_match_all('#https://documents\.astalegale\.net/images/0/[a-f0-9]{32}/\d+-C#i', $h, $m);
    $urls = array_slice(array_values(array_unique($m[0])), 0, $MAX_FOTO);
    if (!$urls) $urls = ["https://documents.astalegale.net/asta/0/{$match['id']}"];

    echo "#$id {$r['city']} -> {$match['id']} (lotto {$match['lotto']}): " . count($urls) . " foto\n";
    if ($prova) continue;

    $salvate = [];
    foreach ($urls as $i => $u) {
        $img = al_get($u . '?w=1280&h=960&format=jpg'); usleep(500000);
        if (strlen($img) < 2000 || !($im = @imagecreatefromstring($img))) continue;
        $n   = count($salvate) + 1;
        $rel = "uploads/properties/$id/astalegale-$n.webp";
        @mkdir("$R/uploads/properties/$id", 0755, true);
        imagewebp($im, "$R/$rel", 85); imagedestroy($im); @chown("$R/$rel", 'www-data');
        $salvate[] = $rel;
    }
    if (!$salvate) { echo "   nessuna foto scaricabile, lascio la mappa\n"; continue; }

    $db->beginTransaction();
    $delSeg->execute([$id]);
    foreach ($salvate as $i => $rel) $insFoto->execute([$id, $rel, "Foto immobile all'asta a {$r['city']}", $i]);

    $db->commit();
    echo "   " . count($salvate) . " foto caricate\n";
    $fatte++;
}
echo "Aste con foto Astalegale: $fatte\n";
