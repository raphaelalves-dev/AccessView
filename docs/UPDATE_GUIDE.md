# Guia de atualização

## Base mínima

A versão 0.10.0 ou superior deve estar instalada porque inclui
`AccessViewUpdater.exe`.

## Criar um pacote

1. atualize `APP_VERSION` no `app.py`;
2. atualize os metadados de versão do instalador, caso também gere um setup;
3. execute `GERAR-ATUALIZACAO.bat`.

Resultado:

```text
ATUALIZACOES\vX.Y.Z\AccessView-Update-vX.Y.Z.zip
```

Uma versão existente não é sobrescrita.

## Aplicar

1. abra o AccessView;
2. clique em `Informações e atualização`;
3. selecione `Carregar atualização`;
4. escolha o ZIP;
5. confirme a elevação administrativa.

O atualizador:

- valida aplicativo, versão e hashes;
- fecha o AccessView;
- cria um backup;
- preserva `config.json`;
- substitui os arquivos;
- registra a atualização em `state.json`;
- reabre o aplicativo;
- restaura os arquivos anteriores se ocorrer uma falha.

## Diagnóstico

```text
C:\ProgramData\AccessView\updates
```

Essa pasta contém logs, estado e os backups mais recentes.
