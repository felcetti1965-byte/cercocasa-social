set -x
mkdir -p out/foto
for id in 2164 3995; do
  n=$([ $id = 2164 ] && echo 40 || echo 26)
  for i in $(seq 1 12); do
    if [ $id = 2164 ]; then f=foto-alta-risoluzione-$i.jpg; else f=miogest-$i.jpg; fi
    curl -sSfL -o out/foto/${id}_$i.jpg "https://www.cercocasaumbria.it/uploads/properties/$id/$f" || true
  done
done
for id in 5005 4998 4997 4996 4995 4994 4992 1443 5003 4761 4595 2938 4807; do
  curl -sSL "https://www.cercocasaumbria.it/immobile.php?id=$id" -o out/foto/p$id.html || true
done
curl -sSfL -o out/foto/logo.png https://www.cercocasaumbria.it/assets/logo-v191.png || true
