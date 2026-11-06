# Agenda & Escalas • versão de teste

Aplicação local com frontend TypeScript, API Python e SQLite persistente. Implementação baseada na revisão 7 do anexo, com as limitações descritas em `docs/STATUS.md`. **Nenhum site foi publicado e nenhuma transação financeira foi executada.**

## Versão de hospedagem e visual

O backend JavaScript e o visual inspirado na referência Fitmas estão preparados para revisão. A API ainda não foi publicada: a revisão automática bloqueou essa ação por conflito com a restrição anterior de produção. Veja `docs/HOSPEDAGEM.md` e `docs/DESIGN.md`. A produção Netlify continua bloqueada.

## Infraestrutura atual

O banco Supabase da agenda foi criado e inicializado com dados fictícios. O repositório GitHub está preparado com bloqueio de builds/publicação no Netlify. O vínculo do repositório pela interface Netlify e a adaptação do backend hospedado ainda precisam ser concluídos. Consulte `docs/INFRAESTRUTURA.md`.

## Adaptação Supabase e GitHub

Foi adicionado um adaptador PostgreSQL com RLS, constraints de intervalo e testes locais, além de workflow GitHub sem implantação. Consulte `docs/SUPABASE.md`. A migração foi aplicada ao novo projeto Supabase da agenda; a configuração inicial e o código foram preparados para o repositório selecionado. O acesso HTTP continua local.

## Abrir

Requer Python 3.12 ou superior. Não precisa instalar bibliotecas Python, Node ou banco externo para executar a versão entregue; o JavaScript compilado está incluído.

1. Extraia este pacote.
2. Abra um terminal na pasta `prisma-agenda-local`.
3. Execute:

```bash
./run-local.sh
```

No Windows, no PowerShell:

```powershell
$env:APP_ENV='local'
$env:SEED_DEMO='1'
$env:BOOTSTRAP_LOCAL='1'
python -m app.server
```

4. Abra **http://127.0.0.1:8765** no navegador do mesmo computador.
5. Use **Entrar como admin — implantação**. Em **Minha conta**, é possível definir a senha posteriormente. Isso encerra todas as sessões desse admin e desativa definitivamente o botão sem senha para essa organização.

O servidor escuta somente `127.0.0.1`, valida Host e Origin e não oferece acesso administrativo remoto. Não exponha por túnel ou proxy. O fluxo remoto autenticado de implantação e a hospedagem Sites estão pendentes. `APP_ENV` diferente de `local` impede iniciar o servidor. `python -m app.maintenance check-production` falha deliberadamente: a entrega não passou pela liberação de produção.

## Perfis fictícios

| Usuário | Perfil | Senha inicial |
|---|---|---|
| admin | Administrador | botão local de implantação; depois a senha definida |
| gerente | Gerência | `Demo@2026!` |
| recepcao | Recepção | `Demo@2026!` |
| professor | Professora Marina / tutor | `Demo@2026!` |
| professor2 | Professor Rafael | `Demo@2026!` |
| estagiario | Lucas / tutor Marina | `Demo@2026!` |
| recepcao2 | Recepção da Unidade Horizonte | `Demo@2026!` |

Os cadastros são fictícios, inclusive registros de conselho e CPFs de teste. Não são registros verificados nem identidades reais autorizadas. Externos e alunos não possuem login. O admin pode criar outras contas individuais no módulo Pessoas. O nome de acesso é único por organização; o admin de outra organização não é compartilhado.

## Dados e comportamento inicial

A inicialização transacional cria uma organização fictícia com duas unidades isoladas e uma terceira unidade de outra organização para testes de isolamento, salas, equipe, tutores, jornadas, alunos, Personal e Nutricionista externos, motivo de atraso demonstrativo, notificações e quatro reservas fictícias futuras. Não recria dados, senhas ou modo de implantação após reinício.

O banco fica em `data/agenda.sqlite`. Ele é criado na primeira abertura e permanece depois de fechar o navegador ou reiniciar o servidor. Não foi incluído banco com sessões no pacote. Para parar, use Ctrl+C. Para reiniciar, execute o mesmo comando. Não exclua o banco para corrigir uma senha esquecida: isso apagaria o histórico; a recuperação segura ainda não está disponível.

A unidade inicial usa **America/Recife**, conforme o documento, e moeda BRL. Horário do cliente não governa regras. Não há relógio fictício na interface: a marcação regular Platinum só funciona quando o servidor estiver em uma sexta-feira; os testes automatizados usam relógios controlados e não mudam o relógio da máquina.

## Roteiro de teste

1. Admin: confira Configurações, cadastre sala/conta e veja a troca de unidades. Confirme que Horizonte tem duração e preço próprios.
2. Recepção: use Agenda → Nova reserva → Consultar disponibilidade. Para Platinum, marque na sexta para segunda a quinta seguintes, com profissional cuja jornada abranja o atendimento.
3. Aluguel externo: escolha sábado/domingo; registre o aceite. A reserva entra em conferência por dez minutos. Em Abrir → Conferir Pix, use valor exato e referência **fictícia**, como `DEMO-PIX-001`. Não transfira dinheiro.
4. Cancele esse aluguel. O financeiro mostra retenção de R$20 e devolução pendente de R$20 para o preço inicial de R$40. Registrar devolução é um evento manual; não é uma ordem bancária.
5. Professor: reserve para si fora da jornada. Cancele e tente criar outra reserva: deve bloquear durante 48h. A recepção não contorna a restrição.
6. Recepção: em Bloquear por imprevisto, alcance uma avaliação. Resolva individualmente por manter ou realocar, com destino válido e ciência do aluno. O bloqueio só é concluído após todas as decisões; falha de destino não perde a origem.
7. Admin: em Configurações, confirme a âncora fictícia. Em Escalas, gere o ciclo, revise o rascunho e publique se não houver erros. A equipe vê só o mês vigente; recepção recebe 403 no endpoint de escala.
8. Professor: solicite cessão de plantão em Permutas. O colega aceita e o admin valida. A aprovação cria nova versão e revalida os ajustes de sexta.
9. Em Minha conta, defina a senha do admin. Abra uma nova sessão e confirme que o botão de implantação desapareceu e que reiniciar não o restaura.

## Verificações

```bash
python3 -m unittest discover -s tests -v
node --check web/app.js
```

Para editar e recompilar o frontend:

```bash
npm install
npm run build
```

TypeScript 7.0.2 foi usado na verificação estrita. Python 3.12.14 foi usado nos testes. O resultado e o escopo estão em `docs/EVIDENCIAS_TESTES.txt` e `docs/STATUS.md`. A execução de testes HTTP precisa permitir sockets locais.

## Backup e restauração

Backup consistente, inclusive com a aplicação funcionando:

```bash
python3 -m app.maintenance backup copia.sqlite
```

Restauração em destino **novo**, com o servidor parado:

```bash
python3 -m app.maintenance restore copia.sqlite --database data/restaurado.sqlite
```

Para abrir esse banco no Linux/macOS:

```bash
APP_ENV=local DATABASE_PATH=data/restaurado.sqlite BOOTSTRAP_LOCAL=1 python3 -m app.server
```

A restauração verifica integridade, relações e versão; não sobrescreve um banco existente e remove sessões restauradas. Senha definida e estado de implantação são preservados. Backups incluem dados pessoais e hashes; guarde em local de acesso restrito. Exportação JSON por unidade está disponível para admin e gerência e não substitui backup integral. Retenção automatizada, criptografia externa e cópia remota são pendências operacionais.

## Organização do código

- `app/domain.py`: calendário, capacidade, validação de CPF/nome/telefone e ciclo.
- `app/service.py`: operações semânticas, autorização, agenda, financeiro, ocorrências e auditoria.
- `app/scheduling.py`: geração e validação de escalas.
- `app/server.py`: HTTP local, sessões, CSRF, rate limit, tarefas a cada 15 segundos.
- `app/db.py`, `migrations/`: persistência, inicialização e dados fictícios.
- `app/maintenance.py`: backup, restauração e bloqueio de produção.
- `web/app.ts`: frontend tipado; `web/app.js`: compilação incluída.
- `tests/`: regras, concorrência, HTTP e restauração.

As tarefas persistem seus efeitos no SQLite e recuperam pendências vencidas após reinício; não dependem da aba do navegador. Não há integração bancária, WhatsApp, e-mail ou Myaghora.

## Sites e publicação

O fluxo local do skill Sites foi utilizado. A instalação deste ambiente não disponibilizou os helpers de projeto/Vinext nem o navegador `cua_repl.js`. Foi implementado um servidor Python local executável e não foi criado um projeto remoto. Nenhum comando de publicação ou de alteração de audiência foi chamado. Para migrar ao Sites, o backend Python/SQLite precisa de adaptação ao runtime suportado e a armazenamento persistente hospedado, com revisão de identidade e tarefas. Consulte `docs/STATUS.md` antes de qualquer implantação.
