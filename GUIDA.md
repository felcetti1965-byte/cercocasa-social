# Video automatici Cercocasa Umbria – Guida

**Dove pubblica**
- Facebook: Pagina https://www.facebook.com/cercocasadovecome
- Instagram: profilo "Cercocasa Dove&Come Umbria" (deve essere Business e collegato alla Pagina Facebook qui sopra)
- TikTok: @cercocasa2020

**Ogni mattina 6 post** (dal 27/10/2026), su Facebook e Instagram:
vendita Terni, vendita Perugia, affitto Terni, affitto Perugia, asta Terni, asta Perugia.
Ogni video: apertura Cercocasa → post con le foto dell'annuncio (grafica nella cartella `grafica/`) → chiusura con i contatti.
Su Facebook va il video 4:5 con la copertina del post; su Instagram il Reel 9:16, con la copertina sul post.
Il programma è `sei_post.py`; pubblica un post ogni 3 minuti (variabile `PAUSA_MINUTI`).
- Pubblicare a mano: Actions → Video giornaliero Cercocasa → Run workflow → togli "Solo prova" e scegli quanti post (1–6).
- Tornare al vecchio sistema (1 annuncio al giorno delle agenzie della rivista, anche su TikTok): crea la variabile `MODO_GIORNALIERO` = `uno`.
- Aggiungere TikTok ai 6 post: variabile `SOCIAL_SEI` = `facebook,instagram,tiktok`.

**Vecchio sistema (`MODO_GIORNALIERO` = `uno`):** uno su Facebook, uno su Instagram, uno su TikTok, ognuno con l'annuncio di **un'agenzia diversa** delle riviste, alternando Perugia e Terni.
Se preferisci lo stesso video su tutti e tre: GitHub → Settings → Secrets and variables → Actions → scheda **Variables** → crea `MODO_POST` = `uguale`.

Ogni giorno, da solo, il programma:
1. sceglie un annuncio nuovo dal sito (ruotando tra le agenzie, mai lo stesso due volte);
2. scarica le foto e crea un video verticale di circa 15 secondi;
3. scrive il testo del post con gli hashtag;
4. lo pubblica come Reel su Instagram e Facebook e lo manda a TikTok.

Ogni giorno tocca a **un'agenzia delle riviste**, alternando Perugia e Terni.

Gira gratis su **GitHub** (non serve toccare il server del sito).

---

## Passo 1 – Metti il programma su GitHub (10 minuti)

1. Crea un account gratuito su https://github.com (puoi usare casadovecome@gmail.com).
2. In alto a destra **+ → New repository**. Nome: `cercocasa-social`. Scegli **Private**. Clicca **Create repository**.
3. Clicca **uploading an existing file** e trascina tutti i file della cartella `cercocasa-social` (anche le cartelle `font` e `musica`). Clicca **Commit changes**.
4. La cartella `.github` a volte non viene caricata perché è "nascosta". Per sicurezza: **Add file → Create new file**, come nome scrivi
   `.github/workflows/video-giornaliero.yml`
   e incolla dentro il contenuto del file con lo stesso nome. **Commit changes**.

## Passo 2 – Fai una prova (senza pubblicare)

1. Nel repository apri la scheda **Actions** (se chiede di attivarle, conferma).
2. A sinistra clicca **Video giornaliero Cercocasa → Run workflow**, lascia la spunta su "Solo prova" → **Run workflow**.
3. Dopo 2–3 minuti apri l'esecuzione: in fondo, alla voce **Artifacts**, scarichi il video e il testo del post.

Se il video ti piace, passa al Passo 3. Fino a quel momento puoi già scaricare il video ogni giorno e pubblicarlo a mano.

## Passo 3 – Collega Instagram

Serve una sola volta. Requisiti: account Instagram **professionale (Business)** collegato alla **Pagina Facebook** "cercocasadovecome".

1. Su Instagram: Impostazioni → Tipo di account e strumenti → **Passa a un account professionale** → Business. Poi collegalo alla Pagina Facebook.
2. Vai su https://developers.facebook.com → **Le mie app → Crea app** → tipo **Business**.
3. Nell'app aggiungi il prodotto **Instagram** (API con accesso tramite Facebook).
4. Su https://business.facebook.com → Impostazioni → **Utenti di sistema** → aggiungi un utente di sistema (Amministratore), assegnagli la Pagina, l'account Instagram e l'app, poi **Genera token** con i permessi:
   `instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement`, `business_management`.
   Questo token **non scade**.
5. Per trovare il numero dell'account Instagram: apri https://developers.facebook.com/tools/explorer, incolla il token e chiedi
   `me/accounts?fields=instagram_business_account`. Il numero che compare in `instagram_business_account → id` è il tuo **IG_USER_ID**.
6. Su GitHub: **Settings → Secrets and variables → Actions → New repository secret**, crea:
   - `IG_USER_ID` = il numero del punto 5
   - `IG_TOKEN` = il token del punto 4

## Passo 3b – Collega Facebook

Usa lo stesso token di Instagram (il token dell'utente di sistema deve avere anche la Pagina assegnata e i permessi `pages_manage_posts` e `publish_video`).
Su GitHub crea il secret `FB_PAGE_ID` = il numero della Pagina Facebook (lo trovi in Pagina → Informazioni → Trasparenza della Pagina, oppure nello stesso risultato di `me/accounts`, alla voce `id`).

## Passo 4 – Collega TikTok

1. Vai su https://developers.tiktok.com, accedi con l'account TikTok e crea un'app.
2. Aggiungi il prodotto **Content Posting API** e i permessi `video.upload` (e `video.publish`).
3. Copia **Client key** e **Client secret** e mettili nei Secrets di GitHub come `TIKTOK_CLIENT_KEY` e `TIKTOK_CLIENT_SECRET`.
4. Il `TIKTOK_REFRESH_TOKEN` si ottiene facendo una volta il login con l'app: questo passaggio lo facciamo insieme.

**Come arriva su TikTok:** all'inizio il video arriva come **bozza** nelle notifiche dell'app TikTok: la apri, aggiungi un suono di tendenza (aiuta molto le visualizzazioni) e pubblichi. Quando TikTok approva la tua app, si può passare alla pubblicazione completamente automatica creando in GitHub la variabile `TIKTOK_MODO` = `diretto`.

## Le agenzie delle riviste

L'elenco è nel file `agenzie_rivista.json`. Per ogni agenzia servono:
- `id`: il numero che vedi nell'indirizzo della sua pagina sul sito (es. `agenzia.php?id=144` → 144);
- `nome`;
- `rivista`: `Perugia` oppure `Terni`.

Ogni mese, quando esce la rivista nuova, aggiorni l'elenco su GitHub (apri il file → matita ✏️ → modifica → Commit). Per sospendere un'agenzia metti `"attiva": false`.

## Musica

Metti 3–5 brani **senza diritti d'autore** (file .mp3) nella cartella `musica` del repository: il programma ne sceglie uno a caso per ogni video. Li trovi gratis su Pixabay Music o nella YouTube Audio Library. Senza brani il video viene creato muto.

## Orario

Pubblica ogni mattina verso le 8 (ora italiana). Per cambiarlo, modifica la riga `cron` nel file `.github/workflows/video-giornaliero.yml` (l'orario è quello inglese: d'estate 2 ore indietro, d'inverno 1 ora).

## Da sapere

- Il file `pubblicati.json` è la memoria degli annunci già usati: non cancellarlo.
- Controlla che nelle condizioni del portale le agenzie accettino la promozione dei loro annunci sui social.
- Per pubblicare un annuncio preciso: `python cercocasa_social.py --id 4586`.
