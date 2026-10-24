#!/bin/bash
# SOLO LETTURA: diagnosi testi città minori + indirizzi schede
R=/var/www/cercocasaumbria-nuovo/site; UA="Mozilla/5.0 Chrome/130"; S=https://www.cercocasaumbria.it
echo "=== FOLIGNO: hero e h1 ==="; curl -sk -A "$UA" "$S/case-vendita/foligno/" -o /tmp/f.html; grep -c 'seo-hero' /tmp/f.html; grep -oE '<h1[^>]*>[^<]*' /tmp/f.html | head -2; grep -oE 'class="[^"]*seo[^"]*"' /tmp/f.html | sort | uniq -c | head
echo "=== INSERIMENTO TESTI NEL CODICE ==="; grep -n 'CCU_TESTI_CITTA' $R/seo-territorio.php | cut -c1-120; grep -c 'class="seo-hero"' $R/seo-territorio.php
echo "=== MACRO / CITY ==="; grep -noE '\$ccuMacro *=.{0,160}' $R/seo-territorio.php | cut -c1-220 | head -3; grep -noE '\$city *=.{0,160}' $R/seo-territorio.php | cut -c1-220 | head -5
echo "=== property_url ==="; awk '/function property_url/{f=1} f{print; n++} n>=25{exit}' $R/includes/bootstrap.php | cut -c1-220
echo "=== USO property_url ==="; grep -rlE --include=*.php "property_url\(" $R --exclude-dir={work,work_v217,ccu_v260,storage,CCU-CORREZIONE-EMAIL} | grep -viE "backup|vecchio|\([0-9]\)" | wc -l
echo "=== CANONICAL 4910 ONLINE ==="; curl -sk -A "$UA" "$S/immobile.php?id=4910" | grep -oE '<link rel="canonical"[^>]*>|<meta property="og:url"[^>]*>'
echo "=== SITEMAP SCHEDE ==="; curl -sk -A "$UA" "$S/sitemap.xml" | grep -oE '<loc>[^<]*immobil[^<]*</loc>' | head -3
echo "=== LEGACY REDIRECT (inizio) ==="; sed -n '1,40p' $R/legacy-redirect.php | cut -c1-200 | grep -vE '^\s*$' | head -30
