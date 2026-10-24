#!/bin/bash
# Testi città V2 + lettura per indirizzi parlanti. Installa solo se il file è valido.
R=/var/www/cercocasaumbria-nuovo/site; BK=/var/backups/ccu-seo-20261024; RAW=https://raw.githubusercontent.com/felcetti1965-byte/cercocasa-social/seo-patch-20261024
mkdir -p $BK; cp -a $R/includes/ccu-testi-citta.php $BK/ccu-testi-citta.php.prima-v2
curl -fsSL "$RAW/ccu-testi-citta.php" -o /tmp/ccu-testi-citta.php || { echo "DOWNLOAD FALLITO"; exit 1; }
if php -l /tmp/ccu-testi-citta.php >/dev/null && grep -q CCU_TESTI_CITTA_V2 /tmp/ccu-testi-citta.php; then cp /tmp/ccu-testi-citta.php $R/includes/ccu-testi-citta.php; echo "TESTI V2 INSTALLATI"; else echo "FILE NON VALIDO, NIENTE MODIFICATO"; exit 1; fi
UA="Mozilla/5.0 Chrome/130"; S=https://www.cercocasaumbria.it
for c in perugia terni foligno spoleto citta-di-castello orvieto; do echo "$c -> codice $(curl -sk -A "$UA" -o /tmp/p.html -w '%{http_code}' "$S/case-vendita/$c/"), parole: $(sed -n '/ccu-city-guide/,/<\/section>/p' /tmp/p.html | sed 's/<[^>]*>/ /g' | wc -w)"; done
echo "######## PUNTO 5: SOLO LETTURA ########"
echo "=== HTACCESS ==="; grep -nvE '^\s*(#|$)' $R/.htaccess | cut -c1-180 | head -70
echo "=== BASE / PERCORSI ==="; grep -c '<base' $R/immobile.php $R/seo-territorio.php; grep -oE 'href="[^"]*style\.css[^"]*"' $R/seo-territorio.php $R/immobile.php | sort -u
echo "=== CANONICAL SCHEDA ==="; grep -noE '\$canonical *=.{0,200}' $R/immobile.php | cut -c1-260
echo "=== SLUGIFY ==="; grep -noE 'function slugify.{0,200}' $R/includes/bootstrap.php | cut -c1-260
echo "=== SITEMAP ==="; ls $R | grep -i sitemap; grep -lE "immobile\.php\?id" $R/sitemap*.php 2>/dev/null
echo "=== FILE CON LINK ALLE SCHEDE ==="; grep -rlE --include=*.php "immobile\.php\?id" $R --exclude-dir={work,work_v217,ccu_v260,storage,CCU-CORREZIONE-EMAIL,admin} | grep -viE "backup|vecchio|\([0-9]\)" | wc -l
echo "=== OUTPUT BUFFER BOOTSTRAP (righe) ==="; grep -nE 'ob_start' $R/includes/bootstrap.php | cut -c1-160
