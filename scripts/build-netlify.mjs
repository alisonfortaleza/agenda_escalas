import {cp,mkdir,rm,readFile,writeFile} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
const context=process.env.CONTEXT||'local-check';
if(context==='production'){console.error('Produção bloqueada: esta etapa permite somente prévia de teste.');process.exit(1);}
execFileSync(process.execPath,['node_modules/typescript/bin/tsc','web/app.ts','--target','es2022','--lib','es2022,dom','--module','es2022','--strict','--outDir','web'],{stdio:'inherit'});
await rm('dist',{recursive:true,force:true});await mkdir('dist',{recursive:true});for(const file of['index.html','app.js','style.css'])await cp('web/'+file,'dist/'+file);await cp('web/assets','dist/assets',{recursive:true});console.log('Frontend compilado. Prévia usa API autenticada; produção permanece bloqueada.');
