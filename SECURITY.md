# Política de segurança

## Dados que nunca devem ser publicados

- `config.json`;
- IPs reais da Tailnet;
- nomes internos de servidores e compartilhamentos;
- usuários Samba;
- senhas do instalador;
- logs de produção;
- pacotes de atualização privados.

## Relato de vulnerabilidades

Não abra uma issue pública contendo credenciais, endereços internos, logs
completos ou detalhes exploráveis.

Envie o relato diretamente ao responsável pelo projeto, incluindo:

- versão afetada;
- passos para reprodução;
- impacto observado;
- evidências sanitizadas;
- sugestão de correção, se disponível.

## Distribuição

- gere senhas do instalador por variável de ambiente;
- publique hashes SHA-256 junto das releases;
- teste atualizações em uma máquina sem dados importantes;
- mantenha permissões Samba como barreira definitiva de somente leitura;
- considere assinatura Authenticode para releases de produção.
