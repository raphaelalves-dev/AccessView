# Contribuição

Este é um projeto proprietário da Click's da Serra.

Contribuições devem ser previamente autorizadas. Para alterações aprovadas:

1. crie uma branch curta e descritiva;
2. não inclua dados reais de infraestrutura;
3. execute as validações locais;
4. descreva riscos e testes realizados no pull request;
5. atualize o `CHANGELOG.md` quando houver mudança de comportamento.

## Validação local

```powershell
python -m py_compile app.py updater.py create_update_package.py
```

Para validar o build completo no Windows:

```text
BUILD-RELEASE.bat
```
