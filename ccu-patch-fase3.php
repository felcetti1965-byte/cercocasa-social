<?php
$R='/var/www/cercocasaumbria-nuovo/site'; $ok=true;
function rep(string $f,string $old,string $new,string $marker):bool{
    $s=file_get_contents($f); if(strpos($s,$marker)!==false){echo basename($f)." ($marker): gia presente\n";return true;}
    $n=substr_count($s,$old); if($n!==1){echo basename($f)." ($marker): NON TROVATO ($n)\n";return false;}
    file_put_contents($f,str_replace($old,$new,$s)); echo basename($f)." ($marker): OK\n"; return true;
}
$b="$R/includes/bootstrap.php";
$ok=rep($b,<<<'O'
return site_url('immobile.php?id='.$id);
O,<<<'N'
/* CCU_URL_A */ $ccuP=function_exists('ccu_property_path')?ccu_property_path($id):''; return site_url($ccuP!==''?$ccuP:'immobile.php?id='.$id);
N,'CCU_URL_A')&&$ok;
$ok=rep($b,<<<'O'
return 'immobile.php?'.http_build_query($query);
O,<<<'N'
/* CCU_URL_B */ $ccuP=function_exists('ccu_property_path')?ccu_property_path($id):''; if($ccuP!==''){unset($query['id']);return '/'.$ccuP.($query?'?'.http_build_query($query):'');} return 'immobile.php?'.http_build_query($query);
N,'CCU_URL_B')&&$ok;
$s=file_get_contents($b);
if(strpos($s,'CCU_URL_C')===false){$s=rtrim($s); if(substr($s,-2)==='?>')$s.="\n<?php"; $s.="\n/* CCU_URL_C */ require_once __DIR__.'/ccu-url-puliti.php';\n"; file_put_contents($b,$s); echo "bootstrap.php (CCU_URL_C): OK\n";}
$ok=rep("$R/immobile.php",<<<'O'
$canonical=property_url($id,(string)$p['title'],(string)$p['city']);
O,<<<'N'
$canonical=property_url($id,(string)$p['title'],(string)$p['city']);
/* CCU_URL_D */ if(($_SERVER['REQUEST_METHOD']??'GET')==='GET'){$ccuPath=(string)parse_url((string)($_SERVER['REQUEST_URI']??''),PHP_URL_PATH);$ccuWant=(string)parse_url($canonical,PHP_URL_PATH);$ccuQ=$_GET;unset($ccuQ['id']);if($ccuWant!=='/immobile.php'&&$ccuPath!==$ccuWant&&(str_starts_with($ccuPath,'/immobile.php')||str_starts_with($ccuPath,'/immobile-'))){header('Location: '.$canonical.($ccuQ?'?'.http_build_query($ccuQ):''),true,301);exit;}}
N,'CCU_URL_D')&&$ok;
$ok=rep("$R/seo-territorio.php",'/* CCU_TESTI_CITTA_V1 */','/* CCU_TESTI_CITTA_V1 */ /* CCU_DBG */ echo "<!-- ccu-dbg ".str_replace("--","- -",htmlspecialchars((string)json_encode(["city"=>$city??null,"zone"=>$zone??null,"type"=>$type??null,"op"=>$operation??null,"page"=>$ccuPage??null,"street"=>$ccuStreetMode??null,"suf"=>$ccuFilterSuffix??null,"count"=>$count??null],JSON_UNESCAPED_UNICODE)))." -->";','CCU_DBG')&&$ok;
$h="$R/.htaccess"; $s=file_get_contents($h);
if(strpos($s,'CCU_URL_PULITI_V1')===false){
    $s2=preg_replace_callback('~^(\s*RewriteEngine On\s*)$~mi',static fn($m)=>$m[1]."\n# CCU_URL_PULITI_V1\n".'RewriteRule ^immobile-(?:[a-z0-9-]+-)?([0-9]+)/?$ immobile.php?id=$1 [END,QSA]',$s,1,$cnt);
    if($cnt===1){file_put_contents($h,$s2);echo ".htaccess: OK\n";}else{echo ".htaccess: NON TROVATO\n";$ok=false;}
}else echo ".htaccess: gia presente\n";
exit($ok?0:1);
