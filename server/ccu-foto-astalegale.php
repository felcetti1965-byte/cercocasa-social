<?php
/*
 * CCU – Foto vere per le aste della provincia di Terni senza foto
 * Per ogni asta TR pubblicata che ha solo il segnaposto o la mappa cerca la scheda
 * ufficiale del lotto e ne scarica le foto (max 6), salvate in webp.
 *
 * Fonti, in ordine:
 *   1. Astalegale (feed RSS provincia di Terni)  – confronto: comune + lotto + prezzo
 *   2. Astegiudiziarie.it (mappa del sito ufficiale, schede dettagliate immobili)
 *                                                – confronto: comune nell'indirizzo + prezzo
 * Toglie segnaposto/mappa. Non modifica nessun altro dato dell'annuncio.
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

$MAX_FOTO       = 6;
$MAX_SCHEDE_AG  = 120;   // massimo schede Astegiudiziarie aperte per comune

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
function al_slug(string $s): string
{
    return trim(str_replace(' ', '-', al_norm($s)), '-');
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
function al_prezzo_ok(array $nostri, array $loro): bool
{
    foreach ($nostri as $p) foreach ($loro as $q) if (abs($p - $q) < 1) return true;
    return false;
}

/* ---------- Fonte 1: Astalegale, feed RSS provincia di Terni ---------- */
$feed = [];
$xml = al_get('https://www.asteimmobili.it/Immobili/Rss?province=tr&regioni=umbria');
if ($xml !== '' && ($x = @simplexml_load_string($xml))) {
    foreach ($x->channel->item as $it) {
        $title = html_entity_decode(strip_tags((string)$it->title), ENT_QUOTES, 'UTF-8');
        $desc  = html_entity_decode(strip_tags((string)$it->description), ENT_QUOTES, 'UTF-8');
        $guid  = trim((string)$it->guid);
        if (!preg_match('/^B\d+$/', $guid) && preg_match('/(B\d{5,})/', (string)$it->link, $g)) $guid = $g[1];
        if (!$guid) continue;
        $feed[] = [
            'id'     => $guid,
            'lotto'  => preg_match('/Lott?o?\s*(?:n\.?\s*)?(\w+)/iu', $title, $l) ? strtolower($l[1]) : '',
            'testo'  => al_norm("$title $desc"),
            'prezzi' => al_prezzi("$title $desc"),
        ];
    }
}
echo count($feed) . " lotti nel feed Astalegale\n";

function foto_astalegale(array $feed, string $citta, string $lotto, array $prezzi): array
{
    $match = null;
    foreach ($feed as $f) {
        if ($citta === '' || !str_contains(' ' . $f['testo'] . ' ', ' ' . $citta . ' ')) continue;
        if ($lotto !== '' && $f['lotto'] !== '' && $f['lotto'] !== $lotto) continue;
        if (!al_prezzo_ok($prezzi, $f['prezzi'])) continue;
        if ($match) return ['doppio', []];
        $match = $f;
    }
    if (!$match) return ['', []];
    $h = al_get("https://www.astalegale.net/Aste/Detail/{$match['id']}"); sleep(1);
    preg_match_all('#https://documents\.astalegale\.net/images/0/[a-f0-9]{32}/\d+-C#i', $h, $m);
    $urls = array_values(array_unique($m[0]));
    if (!$urls) $urls = ["https://documents.astalegale.net/asta/0/{$match['id']}"];
    return ["Astalegale {$match['id']}", array_map(fn($u) => $u . '?w=1280&h=960&format=jpg', $urls)];
}

/* ---------- Fonte 2: Astegiudiziarie.it, mappa del sito ---------- */
$agSchede = null;   // caricata solo se serve
$agCache  = [];
function ag_xml(string $u): string
{
    $x = al_get($u);
    if (strncmp($x, "\x1f\x8b", 2) === 0) $x = (string)@gzdecode($x);   // sitemap compressa
    return $x;
}
function ag_schede(): array
{
    $xml = ag_xml('https://www.astegiudiziarie.it/SiteMap/SchedeDettagliateImmobili');
    preg_match_all('#<loc>\s*([^<]+?)\s*</loc>#i', $xml, $m);
    $loc = $m[1];
    $figli = array_filter($loc, fn($u) => !str_contains($u, 'vendita-asta-'));
    if ($figli && count($figli) === count($loc)) {          // e' un indice di sitemap
        $loc = [];
        foreach ($figli as $f) {
            preg_match_all('#<loc>\s*([^<]+?)\s*</loc>#i', ag_xml(html_entity_decode($f)), $mm);
            $loc = array_merge($loc, $mm[1]);
            sleep(1);
        }
    }
    return array_values(array_unique(array_filter(array_map('html_entity_decode', $loc), fn($u) => str_contains($u, 'vendita-asta-'))));
}
function foto_astegiudiziarie(array &$cache, array $schede, string $cittaSlug, array $prezzi, int $max): array
{
    if ($cittaSlug === '') return ['', []];
    $cand = array_slice(array_values(array_filter($schede, fn($u) => str_contains(strtolower($u), '-' . $cittaSlug . '-'))), 0, $max);
    $trovate = [];
    foreach ($cand as $u) {
        if (!isset($cache[$u])) {
            $h = al_get($u); sleep(1);
            $t = preg_replace('/\s+/u', ' ', html_entity_decode(strip_tags(preg_replace('#<(script|style)[^>]*>.*?</\1>#si', ' ', $h)), ENT_QUOTES, 'UTF-8'));
            preg_match_all('#(?:https?://www\.astegiudiziarie\.it)?/allegato/foto-[^"\'\s<>]+?\.(?:jpe?g|png)/\d+#i', $h, $m);
            $foto = [];
            foreach ($m[0] as $f) {
                $f = str_starts_with($f, 'http') ? $f : 'https://www.astegiudiziarie.it' . $f;
                $foto[strtolower($f)] = $f;
            }
            $cache[$u] = ['prezzi' => al_prezzi($t), 'foto' => array_values($foto)];
        }
        if ($cache[$u]['foto'] && al_prezzo_ok($prezzi, $cache[$u]['prezzi'])) $trovate[$u] = $cache[$u]['foto'];
    }
    if (!$trovate) return ['', []];
    if (count($trovate) > 1) return ['doppio', []];
    $u = array_key_first($trovate);
    return ["Astegiudiziarie " . (preg_match('/-(l\d+-p\d+)/', $u, $x) ? $x[1] : $u), $trovate[$u]];
}

/* ---------- Aste di Terni senza foto vera ---------- */
$sql = "SELECT p.id,p.code,p.city,p.price,p.minimum_bid,p.details_json
        FROM properties p
        WHERE p.operation='asta' AND p.status='pubblicato' AND p.province='TR'
          AND EXISTS (SELECT 1 FROM property_photos f WHERE f.property_id=p.id AND (f.path LIKE '%segnaposto%' OR f.path LIKE '%mappa-posizione%'))
          AND NOT EXISTS (SELECT 1 FROM property_photos f WHERE f.property_id=p.id AND f.path NOT LIKE '%segnaposto%' AND f.path NOT LIKE '%mappa-posizione%')";
if ($soloId) $sql .= " AND p.id=" . $soloId;
$rows = $db->query($sql)->fetchAll(PDO::FETCH_ASSOC);
echo count($rows) . " aste di Terni senza foto vera\n";

$insFoto = $db->prepare("INSERT INTO property_photos(property_id,path,alt_text,sort_order,watermark_status,watermark_version,watermarked_at) VALUES (?,?,?,?,'completata',2,NOW())");
$delSeg  = $db->prepare("DELETE FROM property_photos WHERE property_id=? AND (path LIKE '%segnaposto%' OR path LIKE '%mappa-posizione%')");
$fatte = 0;

foreach ($rows as $r) {
    $id = (int)$r['id'];
    $js = json_decode((string)$r['details_json'], true) ?: [];
    $lotto = strtolower((string)($js['lot'] ?? ''));
    if ($lotto === '' && preg_match('/-(\w+)$/', (string)$r['code'], $m) && substr_count((string)$r['code'], '-') >= 4) $lotto = strtolower($m[1]);
    $prezzi = array_values(array_filter([(float)$r['minimum_bid'], (float)$r['price']]));

    [$fonte, $urls] = foto_astalegale($feed, al_norm((string)$r['city']), $lotto, $prezzi);
    if ($fonte === '') {
        if ($agSchede === null) { $agSchede = ag_schede(); echo count($agSchede) . " schede Astegiudiziarie nella mappa del sito\n"; }
        [$fonte, $urls] = foto_astegiudiziarie($agCache, $agSchede, al_slug((string)$r['city']), $prezzi, $MAX_SCHEDE_AG);
    }
    if ($fonte === '')       { echo "#$id {$r['city']}: nessuna scheda ufficiale con foto trovata\n"; continue; }
    if ($fonte === 'doppio') { echo "#$id {$r['city']}: più schede corrispondenti, salto per sicurezza\n"; continue; }

    $urls = array_slice($urls, 0, $MAX_FOTO);
    echo "#$id {$r['city']} -> $fonte: " . count($urls) . " foto\n";
    if ($prova) continue;

    $salvate = [];
    foreach ($urls as $u) {
        $img = al_get($u); usleep(500000);
        if (strlen($img) < 2000 || !($im = @imagecreatefromstring($img))) continue;
        $n   = count($salvate) + 1;
        $rel = "uploads/properties/$id/foto-ufficiale-$n.webp";
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
echo "Aste con foto vere aggiunte: $fatte\n";
