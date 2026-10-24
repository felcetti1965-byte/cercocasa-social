<?php
/* CCU_URL_PULITI_V1: indirizzi parlanti delle schede, es. /immobile-villa-vendita-magione-1479 */
function ccu_property_slug(string $title,string $city,int $id):string{
    $t=strtolower((string)preg_replace('~[^A-Za-z0-9]+~','-',slugify($title)));
    $c=strtolower((string)preg_replace('~[^A-Za-z0-9]+~','-',slugify((string)preg_replace('~-.*$~','',$city))));
    $t=trim($t,'-'); $c=trim($c,'-');
    if($t==='')$t='immobile';
    if($c!=='' && strpos('-'.$t.'-','-'.$c.'-')===false)$t.='-'.$c;
    if(strlen($t)>70){$t=substr($t,0,70);$p=strrpos($t,'-');if($p!==false&&$p>30)$t=substr($t,0,$p);}
    return 'immobile-'.trim($t,'-').'-'.$id;
}
function ccu_property_paths():array{
    static $map=null; if($map!==null)return $map; $map=[];
    try{
        $st=db()->query("SELECT id,title,city FROM properties WHERE status='pubblicato'");
        foreach($st->fetchAll(PDO::FETCH_ASSOC) as $r){$map[(int)$r['id']]=ccu_property_slug((string)$r['title'],(string)$r['city'],(int)$r['id']);}
    }catch(Throwable $e){$map=[];}
    return $map;
}
function ccu_property_path(int $id):string{$m=ccu_property_paths();return $m[$id]??'';}
function ccu_rewrite_property_links(string $html):string{
    /* CCU_URL_PULITI_V2: anche link con parametri (&lang=, #foto) e apici singoli */
    try{
        if(stripos($html,'<html')===false||strpos($html,'immobile.php?id=')===false)return $html;
        return preg_replace_callback('~(href=)(["\'])((?:https://www\.cercocasaumbria\.it)?/?)immobile\.php\?id=(\d+)((?:&amp;|&)[^"\'#]*)?(#[^"\']*)?\2~',static function($m){
            $p=ccu_property_path((int)$m[4]); if($p==='')return $m[0];
            $q=isset($m[5])&&$m[5]!==''?'?'.preg_replace('~^(&amp;|&)~','',$m[5]):'';
            $h=$m[6]??'';
            return $m[1].$m[2].($m[3]!==''&&$m[3]!=='/'?$m[3]:'/').$p.$q.$h.$m[2];
        },$html)??$html;
    }catch(Throwable $e){return $html;}
}

if(PHP_SAPI!=='cli' && strpos((string)($_SERVER['SCRIPT_NAME']??''),'/admin/')===false){ob_start('ccu_rewrite_property_links');}
