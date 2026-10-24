#!/bin/bash
# SOLO LETTURA: controllo completo del sito (homepage + pagine collegate)
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130 Safari/537.36"; S=https://www.cercocasaumbria.it; D=/tmp/ccu-controllo; rm -rf $D; mkdir -p $D; cd $D
curl -sk -A "$UA" $S/ -o home.html
{ echo /; grep -oE 'href="[^"#]+"' home.html | sed -E 's/href="//;s/"$//;s#^https://www\.cercocasaumbria\.it##' | grep -vE '^(https?:|mailto:|tel:|javascript:|//)' | sed -E 's#^([^/])#/\1#'; for u in /case-vendita/perugia/ /case-vendita/terni/ /case-affitto/perugia/ /aste.php /agenzie.php /prezzi.php /vendi-con-agenzia.php /area-privato.php /pubblica-privato.php /sitemap.xml /robots.txt; do echo $u; done; } | grep -vE '^/admin|\.(jpg|jpeg|png|webp|pdf|css|js|ico|svg)(\?|$)' | sort -u | head -150 > urls.txt
echo "Pagine da controllare: $(wc -l < urls.txt)"
i=0; : > report.txt
while read u; do i=$((i+1)); f=p$i.html
  r=$(curl -sk -A "$UA" -o $f -w '%{http_code} %{redirect_url}' "$S$u"); code=${r%% *}
  if [ "$code" = 301 ] || [ "$code" = 302 ]; then t=${r#* }; r2=$(curl -sk -A "$UA" -o $f -w '%{http_code}' "$t"); code="$code->$r2"; fi
  probs=""
  case "$code" in 200|301-\>200|302-\>200) ;; *) probs="$probs [CODICE $code]";; esac
  if grep -qi '<html' $f; then
    nt=$(grep -o '<title' $f | wc -l); [ "$nt" = 1 ] || probs="$probs [title:$nt]"
    nr=$(grep -oE '<meta name="robots"' $f | wc -l); [ "$nr" -le 1 ] || probs="$probs [robots doppio:$nr]"
    grep -qE '<meta name="robots" content="[^"]*noindex' $f && probs="$probs [noindex]"
    nc=$(grep -oE '<link rel="canonical"' $f | wc -l); [ "$nc" -le 1 ] || probs="$probs [canonical doppio:$nc]"
    nh=$(grep -oE '<h1[ >]' $f | wc -l); [ "$nh" -le 1 ] || probs="$probs [h1:$nh]"
    grep -qiE '(Warning|Fatal error|Deprecated|Notice|Parse error)</b>:|Uncaught |Stack trace' $f && probs="$probs [ERRORE PHP]"
    grep -qE '\b(1[0-9]|[2-9][0-9]*1) (locale|bagno)\b' $f && probs="$probs [plurale]"
    grep -qE '&amp;(#039|quot|amp);' $f && probs="$probs [entita HTML doppie]"
    grep -qE 'immobile\.php\?id=' $f && probs="$probs [link vecchi:$(grep -oE 'immobile\.php\?id=' $f | wc -l)]"
    for a in $(grep -oE 'href="#[a-zA-Z][^"]*"' $f | sed -E 's/href="#//;s/"//' | sort -u); do grep -qE "id=\"$a\"|name=\"$a\"" $f || probs="$probs [#$a senza sezione]"; done
  fi
  [ -n "$probs" ] && echo "$u -> $code$probs" >> report.txt
done < urls.txt
echo "=== PAGINE CON PROBLEMI: $(wc -l < report.txt) su $(wc -l < urls.txt) ==="; cat report.txt | cut -c1-220 | head -60
echo "=== IMMAGINI SENZA ALT (home) ==="; grep -oE '<img [^>]*>' home.html | grep -vc 'alt="[^"]'
echo "=== VELOCITA HOME ==="; curl -sk -A "$UA" -o /dev/null -w "tempo %{time_total}s, peso %{size_download} byte\n" $S/
