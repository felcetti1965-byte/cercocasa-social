<?php
/* CCU_TESTI_CITTA_V2 */
function ccu_testo_citta(string $city,int $count,float $m2):string{
$k=strtr(mb_strtolower(trim($city),'UTF-8'),['à'=>'a','è'=>'e','é'=>'e','ì'=>'i','ò'=>'o','ù'=>'u']);
$T=[
'perugia'=>['Perugia','pubblicati direttamente dalle agenzie immobiliari del territorio: appartamenti, attici, villette, casali, terreni e immobili all’asta',<<<'H'
<h3>Le zone di Perugia</h3>
<p><strong>Centro storico.</strong> Corso Vannucci, Porta Sole, Porta Sant’Angelo e Porta Eburnea: palazzi storici, appartamenti con vista sulla valle e soluzioni adatte anche all’investimento per affitti a studenti e turisti. È la zona con i prezzi al metro quadro più alti, compensati da servizi, negozi e vita culturale a portata di mano.</p>
<p><strong>Elce, Monteluce e Via XX Settembre.</strong> Quartieri residenziali a ridosso del centro, molto richiesti da famiglie e studenti per la vicinanza all’Università degli Studi e all’Università per Stranieri.</p>
<p><strong>San Sisto, Ferro di Cavallo e Madonna Alta.</strong> Zone più recenti, con condomini moderni, parcheggi e spazi verdi. A San Sisto si trovano l’ospedale Santa Maria della Misericordia e il polo universitario di Medicina.</p>
<p><strong>Ponte San Giovanni e Pian di Massiano.</strong> Ponte San Giovanni è il principale polo commerciale della città, con stazione ferroviaria e accesso rapido alla E45. Da Pian di Massiano parte il Minimetrò, che porta in centro in pochi minuti.</p>
<p><strong>Frazioni e campagna.</strong> Castel del Piano, San Marco, Montebello, Ponte Felcino e le colline intorno alla città offrono casali, rustici da ristrutturare e ville con terreno, spesso a prezzi più accessibili e con più spazio esterno.</p>
<h3>Servizi e collegamenti</h3>
<p>Perugia è collegata a Firenze e Roma tramite il raccordo Perugia–Bettolle (A1) e la E45, e a pochi chilometri si trova l’aeroporto internazionale San Francesco d’Assisi. In città ci sono scuole di ogni grado, due università, l’ospedale regionale e una rete di autobus urbani integrata con il Minimetrò.</p>
<p>Usa i filtri per tipologia, prezzo e numero di locali, oppure apri la scheda di ogni annuncio per vedere foto, caratteristiche e storico del prezzo, e contattare l’agenzia direttamente.</p>
H],
'terni'=>['Terni','proposti dalle agenzie immobiliari della zona: appartamenti in centro, villette a schiera, case indipendenti, casali e immobili all’asta',<<<'H'
<h3>Le zone di Terni</h3>
<p><strong>Centro.</strong> Corso Tacito, Piazza della Repubblica, Piazza Tacito e le vie dello shopping: appartamenti in palazzine d’epoca e condomini, con tutti i servizi a piedi e la stazione ferroviaria a pochi minuti.</p>
<p><strong>Città Giardino e Borgo Rivo.</strong> Quartieri residenziali molto apprezzati dalle famiglie, con villette, giardini, scuole e negozi di vicinato.</p>
<p><strong>Borgo Bovio, San Giovanni e Campitello.</strong> Zone popolari e ben servite, dove si trovano spesso appartamenti ampi a prezzi contenuti, adatti alla prima casa o a un investimento da mettere a reddito.</p>
<p><strong>Collescipoli, Cesi e Piediluco.</strong> Borghi e frazioni per chi cerca tranquillità: case in pietra, rustici e ville con vista, a pochi minuti dalla Cascata delle Marmore e dal lago di Piediluco.</p>
<h3>Servizi e collegamenti</h3>
<p>Terni si trova sulla linea ferroviaria Roma–Ancona, con treni diretti per Roma in circa un’ora, ed è collegata all’A1 tramite il raccordo Terni–Orte. In città ci sono l’Azienda Ospedaliera Santa Maria, istituti superiori, la sede ternana dell’Università di Perugia e un’ampia offerta di sport e natura, dal fiume Nera alla Valnerina.</p>
<p>Filtra gli annunci per prezzo, tipologia e zona, consulta lo storico dei prezzi nelle schede e contatta l’agenzia con un clic. Nella sezione aste trovi anche gli immobili in vendita giudiziaria del Tribunale di Terni.</p>
H],
'foligno'=>['Foligno','pubblicati dalle agenzie immobiliari della zona: appartamenti in centro, case a schiera, villette, casali in pianura e in collina e immobili all’asta',<<<'H'
<h3>Le zone di Foligno</h3>
<p><strong>Centro storico.</strong> Piazza della Repubblica, Palazzo Trinci e Corso Cavour: un centro pianeggiante e vivibile, con appartamenti in palazzi storici e negozi a piedi. Qui si corre la Giostra della Quintana, uno degli eventi più sentiti dell’Umbria.</p>
<p><strong>Quartieri residenziali.</strong> Fuori dalle mura la città si allarga in quartieri moderni con condomini, villette e servizi, comodi per chi lavora in città o si sposta spesso in treno.</p>
<p><strong>Frazioni.</strong> Sant’Eraclio, Belfiore, Scanzano e le colline verso Rasiglia offrono case indipendenti e rustici con terreno. Più in alto, l’altopiano di Colfiorito è la scelta per chi cerca aria di montagna.</p>
<h3>Servizi e collegamenti</h3>
<p>Foligno è uno dei principali nodi ferroviari dell’Italia centrale, sulla linea Roma–Ancona e con collegamenti diretti verso Perugia. La statale della Valle Umbra porta a Perugia e Spoleto, mentre la Val di Chienti collega la città alle Marche e al mare Adriatico. In città ci sono l’ospedale San Giovanni Battista, scuole di ogni grado e una ricca rete di negozi e servizi.</p>
<p>Filtra gli annunci per prezzo, tipologia e zona e apri la scheda di ogni immobile per vedere foto, caratteristiche e storico del prezzo.</p>
H],
'spoleto'=>['Spoleto','proposti dalle agenzie immobiliari del territorio: appartamenti nel centro storico, case indipendenti, ville, casali e immobili all’asta',<<<'H'
<h3>Le zone di Spoleto</h3>
<p><strong>Centro storico.</strong> Tra il Duomo, la Rocca Albornoziana e il Ponte delle Torri: appartamenti in palazzi storici e case con vista sulla valle, in una città nota in tutto il mondo per il Festival dei Due Mondi. Adatti anche come seconda casa o investimento per affitti turistici.</p>
<p><strong>Città bassa.</strong> Le zone in pianura, vicine alla stazione e alle vie di scorrimento, offrono condomini e villette più moderni, con parcheggio e servizi.</p>
<p><strong>Frazioni e campagna.</strong> San Giacomo, Eggi, Beroide e le colline verso Monteluco e la Valnerina propongono casali, rustici e ville immerse nel verde, ideali per chi cerca spazio e tranquillità.</p>
<h3>Servizi e collegamenti</h3>
<p>Spoleto si trova sulla linea ferroviaria Roma–Ancona e sulla statale Flaminia, che la collega a Foligno, Terni e Roma. In città ci sono l’ospedale San Matteo degli Infermi, scuole superiori e un’offerta culturale tutto l’anno.</p>
<p>Usa i filtri per tipologia e prezzo e contatta l’agenzia direttamente dalla scheda dell’annuncio.</p>
H],
'citta di castello'=>['Città di Castello','pubblicati dalle agenzie immobiliari dell’Alta Valle del Tevere: appartamenti, case indipendenti, ville, casali e terreni',<<<'H'
<h3>Le zone di Città di Castello</h3>
<p><strong>Centro storico.</strong> All’interno delle mura, tra Palazzo Vitelli e la Pinacoteca comunale: appartamenti in palazzi storici e case su più livelli, con negozi e servizi a piedi. La città ospita anche le collezioni dedicate ad Alberto Burri.</p>
<p><strong>Quartieri fuori le mura.</strong> Zone residenziali con condomini recenti, villette e giardini, comode per famiglie e per chi lavora nelle aziende della valle.</p>
<p><strong>Frazioni.</strong> Trestina, Cerbara, Promano, Riosecco, San Secondo e Lerchi offrono case indipendenti, rustici e casali con terreno, spesso a prezzi più contenuti rispetto alla città.</p>
<h3>Servizi e collegamenti</h3>
<p>Città di Castello è collegata a Perugia e alla Romagna dalla E45. Il territorio ha un tessuto produttivo attivo, un ospedale, scuole di ogni grado e una lunga tradizione nella stampa e nel tessile.</p>
<p>Filtra gli annunci per prezzo, tipologia e zona e apri la scheda di ogni immobile per foto, caratteristiche e contatti dell’agenzia.</p>
H],
'orvieto'=>['Orvieto','proposti dalle agenzie immobiliari del territorio: appartamenti sulla Rupe, case allo Scalo, ville, casali e terreni con vigneto',<<<'H'
<h3>Le zone di Orvieto</h3>
<p><strong>Centro storico sulla Rupe.</strong> Attorno al Duomo e a Corso Cavour: appartamenti in palazzi storici e case con vista sulla campagna, molto richiesti anche come seconda casa e per affitti turistici.</p>
<p><strong>Orvieto Scalo.</strong> La parte bassa della città, con la stazione, i supermercati e i servizi: condomini e villette più moderni, collegati al centro storico dalla funicolare.</p>
<p><strong>Frazioni e campagna.</strong> Sferracavallo, Ciconia, Sugano e le colline intorno al lago di Corbara offrono casali, rustici e ville con terreno e vigneto, in una delle zone vinicole più note dell’Umbria.</p>
<h3>Servizi e collegamenti</h3>
<p>Orvieto ha un casello sull’autostrada A1 e una stazione sulla linea Firenze–Roma, con Roma raggiungibile in circa un’ora. In città ci sono l’ospedale Santa Maria della Stella, scuole superiori e una vivace offerta turistica e culturale.</p>
<p>Usa i filtri per tipologia e prezzo e contatta l’agenzia direttamente dalla scheda dell’annuncio.</p>
H],
];
if(!isset($T[$k]))return '';
[$name,$desc,$body]=$T[$k];
$n=number_format($count,0,',','.');
$prezzo=($m2>=300&&$m2<=6000)?' Il prezzo medio richiesto negli annunci attivi è di circa <strong>'.number_format($m2,0,',','.').' €/m²</strong>, ma cambia molto da zona a zona.':'';
return '<section class="container ccu-city-guide" style="max-width:900px;margin:28px auto;line-height:1.65"><h2>Comprare casa a '.$name.'</h2><p>Su Cercocasa Umbria trovi <strong>'.$n.' case e immobili in vendita a '.$name.'</strong>, '.$desc.'.'.$prezzo.'</p>'.$body.'</section>';
}
