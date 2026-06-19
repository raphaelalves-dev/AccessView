# AccessView

Navegador desktop seguro e somente leitura para compartilhamentos Samba
acessados por uma Tailnet.

O AccessView foi desenvolvido para simplificar a consulta e o download de
arquivos corporativos sem mapear unidades de rede, salvar credenciais ou
expor funções de alteração e exclusão.

> Software pertencente à Click's da Serra. Desenvolvido por Raphael Alves.

## Interface

![Tela de login do AccessView](docs/images/login.png)

## Principais recursos

- autenticação individual com usuário e senha Samba;
- senha mantida somente em memória durante a sessão;
- botão para mostrar ou ocultar a senha;
- navegação por árvore lateral com caminho ativo destacado;
- pastas azuis e interface grafite;
- visualização por miniaturas ou detalhes;
- miniaturas reais de imagens;
- seleção múltipla e download em lote;
- operação estritamente somente leitura;
- logs locais de login, navegação e download;
- atualização por pacote ZIP sem reinstalação;
- validação de versão e integridade SHA-256;
- backup e rollback automático durante atualizações;
- preservação obrigatória do `config.json`.

## Atualizador integrado

![Janela de informações e atualização](docs/images/about.png)

O aplicativo aceita pacotes `AccessView-Update-vX.Y.Z.zip`, fecha o processo,
solicita elevação administrativa, cria um backup, substitui os arquivos e abre
novamente. Pacotes repetidos ou antigos são rejeitados.

![Confirmação de atualização](docs/images/update.png)

## Requisitos

### Uso do aplicativo

- Windows 10 ou Windows 11;
- acesso à Tailnet configurada;
- porta TCP 445 disponível até o servidor;
- conta Samba autorizada.

### Desenvolvimento e build

- Python 3.11 ou superior;
- Inno Setup 6 para gerar o instalador;
- dependências descritas em `requirements.txt`.

## Executar pelo código-fonte

Clone o repositório e entre na pasta:

```powershell
git clone https://github.com/SEU-USUARIO/AccessView.git
cd AccessView
```

Prepare a configuração local:

```powershell
copy config.example.json config.json
```

Edite `config.json`:

```json
{
  "server_ip": "100.100.100.100",
  "shares": ["BACKUP-2026", "SERVER-FILES"],
  "display_name": "Example Server",
  "port": 445,
  "connection_timeout": 8,
  "skip_dfs": true,
  "auth_protocol": "ntlm"
}
```

Depois execute:

```text
PREPARAR-AMBIENTE.bat
EXECUTAR.bat
```

O arquivo `config.json` é ignorado pelo Git para evitar o envio acidental de
endereços e nomes internos.

## Gerar executáveis

Para gerar `AccessView.exe` e `AccessViewUpdater.exe`:

```text
build_exe.bat
```

Os arquivos serão criados em:

```text
dist\AccessView
```

## Gerar instalador e pacote de atualização

Execute:

```text
BUILD-RELEASE.bat
```

Resultados:

```text
output\AccessView-Setup-v0.10.1.exe
output\AccessView-Update-v0.10.1.zip
```

O instalador pode ser protegido por senha sem gravá-la no repositório:

```powershell
$env:ACCESSVIEW_INSTALLER_PASSWORD = "defina-uma-senha-forte"
.\BUILD-RELEASE.bat
```

Sem essa variável, o instalador é gerado sem senha e sem criptografia.

## Gerar apenas uma atualização futura

1. aumente `APP_VERSION` no `app.py`;
2. execute `GERAR-ATUALIZACAO.bat`.

O pacote será salvo em:

```text
ATUALIZACOES\vX.Y.Z\AccessView-Update-vX.Y.Z.zip
```

Consulte [docs/UPDATE_GUIDE.md](docs/UPDATE_GUIDE.md) para o fluxo completo.

## Estrutura

```text
AccessView
├── app.py                         interface e cliente SMB
├── updater.py                     atualizador externo
├── create_update_package.py       geração e assinatura SHA-256 do ZIP
├── AccessView.iss                 instalador Inno Setup
├── BUILD-RELEASE.bat              build completo
├── GERAR-ATUALIZACAO.bat          build de atualização
├── config.example.json            configuração de exemplo
├── docs                           documentação e imagens
└── .github                        workflows e templates
```

## Segurança

- não publique `config.json`;
- não grave senhas no código ou nos BATs;
- configure permissões de leitura também no servidor Samba;
- mantenha regras restritivas na Tailnet;
- use contas individuais para auditoria;
- trate a assinatura SHA-256 como verificação de integridade, não como
  assinatura criptográfica de identidade.

Consulte [SECURITY.md](SECURITY.md) antes de publicar ou distribuir releases.

## Histórico

Veja [CHANGELOG.md](CHANGELOG.md).

## Licença

Este projeto é disponibilizado como código-fonte proprietário. Consulte
[LICENSE.md](LICENSE.md).
