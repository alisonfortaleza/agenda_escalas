# Publicação de demonstração

Publicação explicitamente autorizada pelo responsável em 06/11/2026 e concluída no projeto existente https://agenda-e-escalas.netlify.app.

Frontend: build npm run build:netlify, saída dist, Node 24. Netlify Function api encaminha /api/* para Supabase agenda-api. API JavaScript usa transações e isolamento em PostgreSQL; dados persistem entre deploys. O servidor Python local não está exposto na internet.

Os testes HTTP no endereço público verificaram os cinco perfis fictícios, sessão, CSRF, logout, restrição de escalas para recepção e dados financeiros privados para professores. As duas logomarcas publicadas são idênticas aos PNG do ZIP fornecido.

Acesso de teste: gerente, recepcao, professor, professor2 ou estagiario, senha Demo@2026!. Configuração de senha do admin requer código de uso único entregue ao responsável; ele não está no repositório. Não existe acesso administrativo remoto sem senha.

A aplicação é uma demonstração. Use dados fictícios e referências Pix simuladas. Limitações funcionais e decisões pendentes em STATUS.md; não há declaração de homologação completa.
