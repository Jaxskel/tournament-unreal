import {mkdir,readFile,writeFile,rm} from 'node:fs/promises';
const origin = process.env.GAME_GATEWAY_ORIGIN;
if (!origin) throw new Error('Set GAME_GATEWAY_ORIGIN to the HTTPS game gateway origin');
const url = new URL(origin);
if (url.protocol !== 'https:' || url.origin !== origin || url.username || url.password || /["<>]/.test(origin)) throw new Error('Expected an exact HTTPS origin');
const buildOutput = new URL('./.vercel/output/', import.meta.url);
await rm(buildOutput,{recursive:true,force:true});
await mkdir(new URL('static/',buildOutput),{recursive:true});
const source = new URL('../../browser/public/', import.meta.url);
for (const file of ['index.html','app.js','video-client.js','style.css']) {
  let data = await readFile(new URL(file,source),'utf8');
  if (file === 'index.html') data=data.replace('<head>',`<head>\n  <meta name="tournament-gateway" content="${origin}">`);
  await writeFile(new URL(`static/${file}`,buildOutput),data);
}
await writeFile(new URL('config.json',buildOutput),JSON.stringify({version:3,routes:[{src:'/(.*)',headers:{
  'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer',
  'Content-Security-Policy':`default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self' ${origin} ${origin.replace(/^https:/,'wss:')}; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'`,
  'Permissions-Policy':'camera=(), microphone=(), geolocation=(), fullscreen=(self)'
},continue:true},{handle:'filesystem'}]},null,2));
console.log(`Built web client for ${origin}`);
