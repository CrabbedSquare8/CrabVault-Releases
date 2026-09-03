# CrabVault Releases

Canal oficial de distribuição do CrabVault para Windows x64.

Este repositório publica somente instaladores, verificações SHA-256, notas de versão e os avisos/licenças exigidos pelos componentes distribuídos. O código-fonte do CrabVault não é publicado aqui.

## Instalação

Baixe o arquivo `CrabVault-vX.Y.Z-windows-x64-setup.exe` na seção **Releases**. O CrabVault também pode consultar este repositório pela opção **Configurações → Verificar atualizações**.

## Verificação

Cada instalador acompanha um arquivo `.sha256`. No PowerShell, compare o valor publicado com:

```powershell
Get-FileHash .\CrabVault-vX.Y.Z-windows-x64-setup.exe -Algorithm SHA256
```

Se os valores forem diferentes, não execute o arquivo.

## Licenças e atribuições

O CrabVault é disponibilizado gratuitamente, mas não é software de código aberto. Os termos do aplicativo e os avisos, licenças e fontes correspondentes dos componentes de terceiros acompanham cada release aplicável.

Marvel Rivals e seus materiais pertencem aos respectivos titulares. Este projeto não é afiliado nem endossado por eles.
