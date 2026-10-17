set -e
cd out
mkdir -p ../dati
cp -r foto log.txt ../dati/ 2>/dev/null || true
cp *_iframe.html ../dati/ 2>/dev/null || true
for f in *.png; do ffmpeg -v error -y -i "$f" -q:v 2 "../dati/${f%.png}.jpg"; done
for d in *_cast; do
  python3 - "$d" <<'PY'
import json,sys
d=sys.argv[1]; m=json.load(open(f"{d}/meta.json"))
with open(f"{d}/list.txt","w") as o:
  for i,(f,t) in enumerate(m):
    dur = (m[i+1][1]-t) if i+1<len(m) else 0.5
    o.write(f"file '{f}'\nduration {max(dur,0.001):.4f}\n")
  o.write(f"file '{m[-1][0]}'\n")
PY
  ffmpeg -v error -y -f concat -safe 0 -i "$d/list.txt" -vf "fps=30,scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p" -c:v libx264 -crf 17 -preset slow "../dati/$d.mp4" || echo "fail $d"
done
cd ..; du -sh dati; ls -la dati | head -100
