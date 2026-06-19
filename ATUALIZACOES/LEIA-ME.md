# Pacotes de atualização

Execute `GERAR-ATUALIZACAO.bat` para criar uma nova atualização.

Cada versão será armazenada em sua própria pasta:

```text
ATUALIZACOES
├── ULTIMA-VERSAO.json
├── ULTIMA-VERSAO.txt
├── v0.10.1
│   └── AccessView-Update-v0.10.1.zip
└── v0.10.2
    └── AccessView-Update-v0.10.2.zip
```

O BAT não substitui um pacote que já existe com a mesma versão. Antes de
gerar uma nova atualização, altere `APP_VERSION` no `app.py`.

