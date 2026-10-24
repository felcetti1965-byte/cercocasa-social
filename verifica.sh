#!/bin/bash
# SOLO LETTURA: verifica dei difetti segnalati
UA="Mozilla/5.0 Chrome/130"; S=https://www.cercocasaumbria.it; cd /tmp
curl -sk -A "$UA" $S/case-vendita/perugia/ -o pg.html; curl -sk -A "$UA" $S/ -o hm.html; curl -sk -A "$UA" $S/immobile-villa-all-asta-spoleto-5231 -o sc.html
echo "PERUGIA: link vecchi $(grep -o 'immobile\.php?id=' pg.html | wc -l), nuovi $(grep -oE '/immobile-[a-z0-9-]+-[0-9]+"' pg.html | wc -l), testo $(grep -c ccu-city-guide pg.html), parole $(sed -n '/ccu-city-guide/,/<\/section>/p' pg.html | sed 's/<[^>]*>/ /g' | wc -w), apostrofi rotti $(grep -o '&amp;#039;' pg.html | wc -l), affitto in vendita $(grep -oi 'affitto via della concordia' pg.html | wc -l)"
echo "HOME: href #riviste $(grep -c 'href="#riviste"' hm.html), sezione riviste $(grep -c 'id="riviste"' hm.html), href #prezzi $(grep -c 'href="#prezzi"' hm.html), sezione prezzi $(grep -c 'id="prezzi"' hm.html), apostrofi rotti $(grep -o '&amp;#039;' hm.html | wc -l)"
echo "SCHEDA: codice $(curl -sk -A "$UA" -o /dev/null -w '%{http_code}' $S/immobile-villa-all-asta-spoleto-5231), '11 locale' $(grep -oE '\b1?[1-9]+ locale\b' sc.html | grep -v '^1 ' | wc -l), rata zero $(grep -o 'Rata da € 0 ' sc.html | wc -l), 0 planimetrie $(grep -o '0 Planimetrie' sc.html | wc -l)"
echo "ESEMPI 'locale':"; grep -oE '.{0,40}\b[0-9]+ locale\b.{0,20}' sc.html | sed 's/<[^>]*>//g' | head -3
echo "ESEMPI apostrofi:"; grep -oE '.{0,40}&amp;#039;.{0,20}' pg.html | sed 's/<[^>]*>//g' | head -3
