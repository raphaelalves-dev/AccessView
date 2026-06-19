# Publicar no GitHub

## Configuração sugerida

- nome: `AccessView`;
- descrição: `Navegador seguro e somente leitura para compartilhamentos Samba via Tailnet.`;
- visibilidade recomendada: `Private`;
- não adicione README, `.gitignore` ou licença pela interface, pois esses
  arquivos já existem no projeto.

## Publicação pela linha de comando

Depois de criar um repositório vazio:

```powershell
git init
git add .
git commit -m "Initial AccessView 0.10.1 release"
git branch -M main
git remote add origin https://github.com/SEU-USUARIO/AccessView.git
git push -u origin main
```

## Antes do primeiro push

```powershell
python scripts\validate_repository.py
python -m unittest discover -s tests -v
```

Confirme que `git status` não mostra:

- `config.json`;
- pastas `venv`, `build`, `dist` ou `output`;
- logs;
- instaladores e atualizações gerados;
- dados reais de infraestrutura.

## Senha do instalador

Defina a senha somente na sessão local:

```powershell
$env:ACCESSVIEW_INSTALLER_PASSWORD = "uma-senha-nova-e-forte"
.\BUILD-RELEASE.bat
```

Não use novamente uma senha que já tenha sido gravada no histórico do projeto.
