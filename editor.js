// Lightweight indentation assistance while typing; does not reformat pasted code.
function pythonIndentBefore(text){
 const line=text.slice(text.lastIndexOf('\n')+1);
 const indent=line.match(/^[\t ]*/)[0];
 let quote=null,triple=false,comment=false,depth=0,statement='';
 // Ignore quoted colons and comments, and keep multiline headers together.
 for(let i=0;i<text.length;i++){
  const ch=text[i];
  if(comment){if(ch!=='\n')continue;comment=false}
  if(quote){
   if(ch==='\\'){i++;continue}
   if(triple&&text.slice(i,i+3)===quote.repeat(3)){quote=null;triple=false;i+=2}
   else if(!triple&&ch===quote)quote=null;
   continue;
  }
  if(ch==='"'||ch==="'"){
   quote=ch;triple=text.slice(i,i+3)===ch.repeat(3);
   if(triple)i+=2;
   statement+='s';continue;
  }
  if(ch==='#'){comment=true;continue}
  if('([{'.includes(ch))depth++;
  if(')]}'.includes(ch))depth=Math.max(0,depth-1);
  if(ch==='\n'){
   if(depth===0&&!statement.trimEnd().endsWith('\\'))statement='';
   else statement+=' ';
  }else statement+=ch;
 }
 const block=/^(?:(?:async\s+)?(?:def|for|with)\b|if\b|elif\b|else\b|while\b|try\b|except\b|finally\b|class\b|match\b|case\b)/;
 const opensBlock=!quote&&depth===0&&block.test(statement.trim())&&statement.trimEnd().endsWith(':');
 // Follow existing tab indentation, otherwise use Python's four-space convention.
 return indent+(opensBlock?(indent.includes('\t')?'\t':'    '):'');
}
source.addEventListener('keydown',e=>{
 if(e.isComposing||e.defaultPrevented||e.ctrlKey||e.metaKey||e.altKey)return;
 const start=source.selectionStart,end=source.selectionEnd;
 if(e.key==='Enter'&&!e.shiftKey){
  e.preventDefault();
  const indent=pythonIndentBefore(source.value.slice(0,start));
  source.setRangeText('\n'+indent,start,end,'end');
 }else if(e.key==='Tab'){
  e.preventDefault();
  if(e.shiftKey){
   const lineStart=source.value.lastIndexOf('\n',start-1)+1;
   const leading=source.value.slice(lineStart).match(/^(?:\t| {1,4})/);
   if(!leading)return;
   const count=leading[0].length;
   source.setRangeText('',lineStart,lineStart+count,'preserve');
   source.setSelectionRange(Math.max(lineStart,start-count),Math.max(lineStart,end-count));
  }else source.setRangeText('    ',start,end,'end');
 }else return;
 source.dispatchEvent(new Event('input',{bubbles:true}));
});
