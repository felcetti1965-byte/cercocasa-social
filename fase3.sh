#!/bin/bash
# Indirizzi parlanti delle schede + diagnosi testi città. Se un test fallisce ripristina tutto da solo.
R=/var/www/cercocasaumbria-nuovo/site; BK=/var/backups/ccu-seo-20261024/fase3; RAW=https://raw.githubusercontent.com/felcetti1965-byte/cercocasa-social/seo-patch-20261024
UA="Mozilla/5.0 Chrome/130"; S=https://www.cercocasaumbria.it
FILES="includes/bootstrap.php immobile.php seo-territorio.php .htaccess"
mkdir -p $BK; for f in $FILES; do mkdir -p "$BK/$(dirname $f)"; cp -a "$R/$f" "$BK/$f"; done; echo "Backup in $BK"
ripristina(){ for f in $FILES; do cp -a "$BK/$f" "$R/$f"; done; rm -f $R/includes/ccu-url-puliti.php; echo ">>> $1 -> RIPRISTINATO TUTTO COME PRIMA"; exit 1; }
curl -fsSL "$RAW/ccu-url-puliti.php" -o $R/includes/ccu-url-puliti.php && curl -fsSL "$RAW/ccu-patch-fase3.php" -o /tmp/ccu-patch-fase3.php || ripristina "download fallito"
php /tmp/ccu-patch-fase3.php || ripristina "modifica non applicata"
for f in includes/bootstrap.php includes/ccu-url-puliti.php immobile.php seo-territorio.php; do php -l $R/$f >/dev/null || ripristina "errore sintassi in $f"; done
echo "=== TEST ==="
r=$(curl -sk -A "$UA" -o /dev/null -w '%{http_code} %{redirect_url}' "$S/immobile.php?id=4910"); echo "vecchio indirizzo 4910 -> $r"
case "$r" in "301 $S/immobile-"*) ;; *) ripristina "il vecchio indirizzo non reindirizza";; esac
NEW=${r#301 }; c=$(curl -sk -A "$UA" -o /tmp/n.html -w '%{http_code}' "$NEW"); echo "nuovo indirizzo -> $c $NEW"
[ "$c" = 200 ] || ripristina "il nuovo indirizzo non risponde 200"
grep -q "<link rel=\"canonical\" href=\"$NEW\"" /tmp/n.html || ripristina "canonical non aggiornato"
n=0; for css in $(grep -oE '<link rel="stylesheet" href="[^"]+"' /tmp/n.html | sed -E 's/.*href="([^"]+)"/\1/' | grep -v '^https\?://fonts'); do case "$css" in http*) u=$css;; /*) u=$S$css;; *) u=$S/$css;; esac; n=$((n+1)); cc=$(curl -sk -A "$UA" -o /dev/null -w '%{http_code}' "$u"); [ "$cc" = 200 ] || ripristina "foglio di stile non caricato: $css ($cc)"; done; echo "fogli di stile caricati: $n"; [ $n -gt 0 ] || ripristina "nessun foglio di stile"
w=$(curl -sk -A "$UA" -o /dev/null -w '%{http_code} %{redirect_url}' "$S/immobile-nome-sbagliato-4910"); echo "nome sbagliato -> $w"
[ "$w" = "301 $NEW" ] || ripristina "redirect nome sbagliato"
for u in / /case-vendita/perugia/ /immobile.php?id=4707; do c=$(curl -sk -A "$UA" -o /tmp/x.html -w '%{http_code}' -L "$S$u"); echo "$u -> $c"; [ "$c" = 200 ] || ripristina "$u non risponde"; done
echo "link schede in home: vecchi $(curl -sk -A "$UA" $S/ | grep -o 'immobile\.php?id=' | wc -l), nuovi $(curl -sk -A "$UA" $S/ | grep -o 'href="/immobile-' | wc -l)"
echo "sitemap: $(curl -sk -A "$UA" $S/sitemap.xml | grep -oE '<loc>[^<]*immobile[^<]*</loc>' | head -2 | tr '\n' ' ')"
grep -nE "immobile\.php\?id" $R/sitemap.php | cut -c1-200 | head -3
echo "=== TUTTO OK ==="
echo "=== DIAGNOSI TESTI ==="; for c in perugia foligno; do echo "$c: $(curl -sk -A "$UA" "$S/case-vendita/$c/" | grep -oE '<!-- ccu-dbg [^>]*-->')"; done
