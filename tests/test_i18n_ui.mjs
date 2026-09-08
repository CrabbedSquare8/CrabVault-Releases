import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../frontend/i18n.js', import.meta.url), 'utf8');
const html = fs.readFileSync(new URL('../frontend/index.html', import.meta.url), 'utf8');
const alerts = [], confirmations = [];
class Element {}
const root = new Element(); root.nodeType = 1; root.hasAttribute = () => false;
const document = {
  body: root,
  documentElement: root,
  createTreeWalker: () => ({currentNode:null, nextNode:() => false}),
};
class MutationObserver { constructor(callback) { this.callback = callback; } observe() {} }
const window = {
  alert: message => alerts.push(message),
  confirm: message => { confirmations.push(message); return true; },
};
window.window = window;
const context = vm.createContext({window, document, Element, MutationObserver,
  Node:{TEXT_NODE:3}, NodeFilter:{SHOW_ELEMENT:1, SHOW_TEXT:4}});
vm.runInContext(source, context);

window.setUiLanguage('en');
assert.equal(window.getUiLanguage(), 'en');
assert.equal(window.uiText('Configurações'), 'Settings');
assert.equal(window.uiText('CATÁLOGO DE PERSONAGENS E SKINS'), 'CHARACTER AND SKIN CATALOG');
assert.equal(window.uiText('Atualizar catálogo agora'), 'Update catalog now');
assert.equal(window.uiText('Sem FModel ou instalação de .NET. Na primeira abertura, o CrabVault baixa e verifica o mapping, zlib e Oodle 2.9.10. A Oodle vem do projeto comunitário'),
  'No FModel or .NET installation. On first use, CrabVault downloads and verifies the mapping, zlib, and Oodle 2.9.10. Oodle comes from the community project');
assert.equal(window.uiText('sob os termos da Unreal Engine; depois tudo é reutilizado localmente.'),
  'under the Unreal Engine terms; everything is then reused locally.');
assert.equal(window.uiText('Preserva o ZIP/RAR/7z original. Se você selecionar PAK/UCAS/UTOC soltos, reúne todos eles em um novo ZIP dentro de'),
  'Keeps the original ZIP/RAR/7z. If you select loose PAK/UCAS/UTOC files, all of them are collected into a new ZIP inside');
assert.equal(window.uiText('A cópia instalável em'), 'The installable copy in');
assert.match(window.uiText('continua existindo nas duas opções. Arquivos que já estão na biblioteca privada nunca são apagados. Ao importar vários pacotes soltos juntos, um único ZIP guarda todos eles sem misturar arquivos com nomes iguais.'), /remains available with either option/);
assert.equal(window.uiText('Salva cópias sequenciais em'), 'Saves sequential copies in');
assert.match(window.uiText('ou restaura catálogo, tags, capas cadastradas, componentes, perfis e configurações. Arquivos de mods e mídias não são copiados.'), /or restores the catalog/);
assert.match(html, /id="setting-update-character-catalog"/);
assert.match(html, /github\.com\/donutman07\/MarvelRivalsCharacterIDs/);
assert.equal(window.uiText('3 selecionados'), '3 selected');
assert.equal(window.uiText('3 arquivo(s) · Prioridade 2'), '3 file(s) · Priority 2');
assert.equal(window.uiText('1 operação(ões) interrompida(s) aguardam revisão. Nenhum arquivo será alterado automaticamente.'),
  '1 interrupted operation(s) await review. No file will be changed automatically.');
assert.equal(window.uiText('ARQUIVOS (6 ARQUIVOS)'), 'FILES (6 FILES)');
assert.equal(window.uiText('Importação de mod'), 'Mod import');
assert.equal(window.uiText('Descartar somente a preparação incompleta; os originais foram preservados.'),
  'Discard only the incomplete preparation; the original files were preserved.');
assert.equal(window.uiText('Remover mod (preserva imagens e ZIP/RAR/7z)'), 'Remove mod (keeps images and ZIP/RAR/7z)');
assert.equal(window.uiText('Excluir permanentemente (apaga tudo)'), 'Delete permanently (deletes everything)');
assert.equal(window.uiText('Adicionar tag…'), 'Add tag…');
assert.equal(window.uiText('Mover para…'), 'Move to…');
assert.equal(window.uiText('Todos (16)'), 'All (16)');
assert.equal(window.uiText('Variações (12)'), 'Variations (12)');
assert.equal(window.uiText('Complementos (4)'), 'Add-ons (4)');
assert.equal(window.uiText('Histórico (0)'), 'History (0)');
assert.equal(window.uiText('Corrigir'), 'Correct');
assert.equal(window.uiText('Nenhuma tag adicionada.'), 'No tags added.');
assert.equal(window.uiText('Diagnóstico'), 'Diagnostics');
assert.equal(window.uiText('Relações'), 'Relationships');
assert.equal(window.uiText('Mais ações do componente'), 'More component actions');
assert.equal(window.uiText('Atualizar, restaurar versão ou remover'), 'Update, restore a version, or remove');
assert.equal(window.uiText('Gerenciar componente'), 'Manage component');
assert.equal(window.uiText('Excluído permanentemente: A_Test_9999999_P'), 'Permanently deleted: A_Test_9999999_P');
assert.equal(window.uiText('Desativados 2 mod(s)'), 'Disabled 2 mod(s)');
assert.equal(window.uiText('Ativado: A_Test_9999999_P'), 'Enabled: A_Test_9999999_P');
assert.equal(window.uiText('Componente ativado: A_Extra_9999999_P'), 'Component enabled: A_Extra_9999999_P');
assert.equal(window.uiText('Prévia 3D preparada: A_Test_9999999_P'), '3D preview prepared: A_Test_9999999_P');
assert.equal(window.uiText('Não foi possível preparar o modelo.'), 'Could not prepare the model.');
assert.equal(window.uiText('Não encontrei a pasta Paks a partir do caminho de mods configurado.'),
  'Could not find the Paks folder from the configured mods path.');
assert.equal(window.uiText('Não foi possível preparar o modelo 3D: Não encontrei a pasta Paks a partir do caminho de mods configurado.'),
  'Could not prepare the 3D model: Could not find the Paks folder from the configured mods path.');
window.alert('Nenhum mod encontrado.');
window.confirm('Remover mod');
assert.deepEqual(alerts, ['No mods found.']);
assert.deepEqual(confirmations, ['Remove mod']);

window.setUiLanguage('pt-BR');
assert.equal(window.getUiLanguage(), 'pt-BR');
assert.equal(window.uiText('Configurações'), 'Configurações');

console.log('Global language: catalog, patterns, alerts, confirmations and language switching passed.');
