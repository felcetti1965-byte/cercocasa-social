#!/bin/bash
# Link schede rimasti nel formato vecchio -> nuovo formato. Ripristino automatico se qualcosa non risponde.
R=/var/www/cercocasaumbria-nuovo/site; BK=/var/backups/ccu-seo-20261024; RAW=https://raw.githubusercontent.com/felcetti1965-byte/cercocasa-social/COMMIT
UA="Mozilla/5.0 Chrome/130"; S=https://www.cercocasaumbria.it; F=$R/includes/ccu-url-puliti.php
conta(){ for u in /agenzia.php?id=144 /agenzia.php?id=126 /immobile-villa-vendita-narni-1839 "/articolo.php?slug=nuove-case-in-vendita-a-terni-gli-annunci-della-settimana-20261021"; do c=$(curl -sk -A "$UA" -o /tmp/c.html -w '%{http_code}' "$S$u"); echo "  $u -> $c, link vecchi in href: $(grep -oE "href=[\"'][^\"']*immobile\.php\?id=" /tmp/c.html | wc -l), altrove: $(( $(grep -o 'immobile\.php?id=' /tmp/c.html | wc -l) - $(grep -oE "href=[\"'][^\"']*immobile\.php\?id=" /tmp/c.html | wc -l) ))"; [ "$c" = 200 ] || return 1; done; }
echo "PRIMA:"; conta
echo "Esempi link vecchi (agenzia 144):"; curl -sk -A "$UA" "$S/agenzia.php?id=144" | grep -oE '.{0,40}immobile\.php\?id=[0-9]+.{0,25}' | sed -E 's/[0-9]{3,}/N/g' | sort | uniq -c | sort -rn | head -5
cp -a $F $BK/ccu-url-puliti.php.v1
curl -fsSL "$RAW/ccu-url-puliti.php" -o /tmp/ccu-url-puliti.php && php -l /tmp/ccu-url-puliti.php >/dev/null && grep -q CCU_URL_PULITI_V2 /tmp/ccu-url-puliti.php && cp /tmp/ccu-url-puliti.php $F || { echo "FILE NON VALIDO, niente modificato"; exit 1; }
echo "DOPO:"; conta || { cp -a $BK/ccu-url-puliti.php.v1 $F; echo ">>> una pagina non risponde: RIPRISTINATO"; exit 1; }
c=$(curl -sk -A "$UA" -o /dev/null -w '%{http_code}' $S/); [ "$c" = 200 ] || { cp -a $BK/ccu-url-puliti.php.v1 $F; echo ">>> home non risponde: RIPRISTINATO"; exit 1; }
echo "=== OK ==="
echo "=== H1 IN aste.php ==="; grep -noE '.{0,60}<h1[^>]*>.{0,80}' $R/aste.php | cut -c1-200
