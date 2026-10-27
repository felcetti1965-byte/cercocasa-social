<?php
/*
 * Cercocasa Umbria – pagina "link nella bio" per Instagram e TikTok.
 * Mostra gli annunci pubblicati sui social negli ultimi giorni, ognuno con il pulsante per aprirlo.
 * I dati arrivano dal file pubblicati.json del sistema automatico su GitHub (aggiornato ogni mattina).
 * Da mettere in: /var/www/cercocasaumbria-nuovo/site/oggi.php  ->  https://www.cercocasaumbria.it/oggi.php
 */
header('Content-Type: text/html; charset=utf-8');
header('X-Robots-Tag: noindex, follow');

$FONTE = 'https://raw.githubusercontent.com/felcetti1965-byte/cercocasa-social/main/pubblicati.json';
$CACHE = sys_get_temp_dir() . '/cercocasa-oggi.json';
$MAX = 12;

function leggi_fonte($url) {
    if (function_exists('curl_init')) {
        $c = curl_init($url);
        curl_setopt_array($c, [CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 8, CURLOPT_FOLLOWLOCATION => true]);
        $t = curl_exec($c);
        $ok = curl_getinfo($c, CURLINFO_HTTP_CODE) === 200;
        curl_close($c);
        if ($ok && $t) return $t;
    }
    return @file_get_contents($url, false, stream_context_create(['http' => ['timeout' => 8]]));
}

$json = (is_file($CACHE) && time() - filemtime($CACHE) < 300) ? file_get_contents($CACHE) : false;
if ($json === false) {
    $json = leggi_fonte($FONTE);
    if ($json !== false && json_decode($json, true)) {
        @file_put_contents($CACHE, $json);
    } elseif (is_file($CACHE)) {
        $json = file_get_contents($CACHE);   // se GitHub non risponde uso l'ultima copia
    }
}
$dati = $json ? json_decode($json, true) : [];
$voci = array_values(array_filter($dati['pubblicati'] ?? [], function ($p) { return !empty($p['sei']); }));
usort($voci, function ($a, $b) { return strcmp($b['data'] ?? '', $a['data'] ?? ''); });
$visti = [];
$annunci = [];
foreach ($voci as $v) {
    $id = (int)($v['id'] ?? 0);
    if (!$id || isset($visti[$id])) continue;
    $visti[$id] = true;
    $annunci[] = $v;
    if (count($annunci) >= $MAX) break;
}

$ETICHETTA = ['vendita' => 'In vendita', 'affitto' => 'In affitto', 'asta' => 'All’asta'];
function e($s) { return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8'); }
function giorno($data) {
    $t = strtotime(substr((string)$data, 0, 10));
    if (!$t) return '';
    if (date('Y-m-d', $t) === date('Y-m-d')) return 'Oggi';
    if (date('Y-m-d', $t) === date('Y-m-d', strtotime('-1 day'))) return 'Ieri';
    $mesi = ['gen', 'feb', 'mar', 'apr', 'mag', 'giu', 'lug', 'ago', 'set', 'ott', 'nov', 'dic'];
    return date('j', $t) . ' ' . $mesi[(int)date('n', $t) - 1];
}
?><!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, follow">
<title>Annunci dai nostri social | Cercocasa Umbria</title>
<link rel="icon" href="/assets/logo-v191.png">
<style>
:root{--oro:#DB9C12;--scuro:#1F1F1F;--fondo:#F4F2ED;--testo:#1F1F1F;--grigio:#5E5E5E}
*{box-sizing:border-box}
body{margin:0;background:var(--fondo);color:var(--testo);font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header{background:var(--scuro);padding:18px 16px;text-align:center}
header img{height:56px;width:auto}
main{max-width:560px;margin:0 auto;padding:20px 16px 40px}
h1{font-size:22px;margin:4px 0 4px}
.sotto{color:var(--grigio);margin:0 0 20px;font-size:15px}
.card{display:block;background:#fff;border-radius:18px;overflow:hidden;margin-bottom:18px;text-decoration:none;color:inherit;box-shadow:0 2px 10px rgba(0,0,0,.08)}
.foto{position:relative;aspect-ratio:16/10;background:#d9d6cf}
.foto img{width:100%;height:100%;object-fit:cover;display:block}
.tag{position:absolute;top:12px;left:12px;background:#fff;color:var(--scuro);font-weight:700;font-size:13px;padding:6px 12px;border-radius:999px;text-transform:uppercase;letter-spacing:.04em}
.tag.asta{background:var(--oro)}
.quando{position:absolute;top:12px;right:12px;background:var(--scuro);color:#fff;font-size:12px;font-weight:600;padding:6px 10px;border-radius:999px}
.info{padding:14px 16px 16px}
.prezzo{font-size:24px;font-weight:800}
.titolo{font-size:15px;margin:4px 0 2px;line-height:1.35}
.dove{color:var(--grigio);font-size:14px}
.bottone{display:block;margin-top:12px;background:var(--oro);color:var(--scuro);text-align:center;font-weight:700;padding:13px;border-radius:12px;font-size:16px}
.vuoto{background:#fff;border-radius:18px;padding:24px;text-align:center}
.tutti{display:block;text-align:center;margin-top:8px;color:var(--scuro);font-weight:700}
</style>
</head>
<body>
<header><a href="/"><img src="/assets/logo-v191.png" alt="Cercocasa Umbria"></a></header>
<main>
<h1>Gli annunci dei nostri video</h1>
<p class="sotto">Tocca un annuncio per vedere tutte le foto e contattare l’agenzia.</p>
<?php if (!$annunci): ?>
  <div class="vuoto">Gli annunci di oggi stanno arrivando. Intanto <a href="/">guarda tutti gli annunci</a>.</div>
<?php endif; ?>
<?php foreach ($annunci as $v):
    $id = (int)$v['id'];
    $url = !empty($v['url']) ? $v['url'] : "/immobile.php?id=$id";
    $tipo = explode('-', $v['sei'] ?? '')[0];
    $titolo = $v['titolo'] ?? '';
    if ($titolo === '') $titolo = 'Annuncio ' . $id;
?>
  <a class="card" href="<?= e($url) ?>">
    <div class="foto">
      <?php if (!empty($v['foto'])): ?><img src="<?= e($v['foto']) ?>" alt="<?= e($titolo) ?>" loading="lazy"><?php endif; ?>
      <span class="tag <?= $tipo === 'asta' ? 'asta' : '' ?>"><?= e($ETICHETTA[$tipo] ?? 'Annuncio') ?></span>
      <span class="quando"><?= e(giorno($v['data'] ?? '')) ?></span>
    </div>
    <div class="info">
      <?php if (!empty($v['prezzo'])): ?><div class="prezzo"><?= e($v['prezzo']) ?></div><?php endif; ?>
      <div class="titolo"><?= e($titolo) ?></div>
      <div class="dove"><?= e(trim(($v['comune'] ?? '') . ' · codice ' . $id, ' ·')) ?></div>
      <span class="bottone">Vedi l’annuncio</span>
    </div>
  </a>
<?php endforeach; ?>
<a class="tutti" href="/">Tutti gli annunci su cercocasaumbria.it →</a>
</main>
</body>
</html>
