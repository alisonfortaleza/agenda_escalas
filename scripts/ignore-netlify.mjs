// Netlify: zero cancels a Git build; one proceeds.
process.exit(process.env.CONTEXT==='production'?0:1);
