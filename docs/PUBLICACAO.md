# Próxima etapa de implantação — não executada

Esta versão roda apenas no computador local e não pode ser enviada diretamente ao runtime de Sites. Nenhuma URL remota foi criada. O servidor usa biblioteca padrão Python para teste local e a persistência SQLite é local.

Antes de uma implantação futura:

1. Concluir as funcionalidades parciais e decisões do documento STATUS.
2. Adaptar as operações ao runtime hospedado suportado pelo Sites e a um banco relacional persistente hospedado. Preservar transações de reserva, trava por CPF, isolamento e snapshots.
3. Configurar identidade, TLS, recuperação segura e tarefas de fundo independentes do processo web; manter rate limit, CSRF, sessões e auditoria.
4. Manter ambiente de implantação remotamente protegido. A entrada temporária de admin só pode ser habilitada depois de autenticar o responsável na camada externa ou por uma credencial segura de implantação. Não aceitar nome admin como prova de identidade.
5. Definir a senha do admin e verificar o estado no servidor antes de liberar qualquer painel público. Nunca publicar as contas fictícias como contas de operação, nem reinicializar o banco existente para reabrir implantação.
6. Fazer migração, backup/restauração, verificação visual e testes de integração reais no ambiente protegido. Validar permissões de organização/unidade e processos manuais de pagamento sem transferência no teste.
7. Executar a checagem obrigatória de preparação para publicação. O comando atual falha de propósito porque esta versão não atende à liberação de produção.
8. Somente em etapa autorizada, usar os helpers oficiais do Sites, registrar identidade real do projeto e salvar/publicar a versão conferida, preservando audiência protegida. Não inventar um project_id.

Não foram criadas credenciais bancárias, integrações externas ou contas de produção. Contratos, preços e políticas precisam de validação da academia. Não há certificação jurídica automática das regras de jornada.
