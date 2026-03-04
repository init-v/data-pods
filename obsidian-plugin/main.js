/**
 * Data Pods Connector - Obsidian Plugin
 * Search and insert content from your Data Pods
 */

const { Plugin, Setting, FuzzyMatch, FuzzySuggestModal } = require('obsidian');

class DataPodsPlugin extends Plugin {
  async onload() {
    console.log('Loading Data Pods Connector...');
    
    // Register command to search pods
    this.addCommand({
      id: 'search-data-pods',
      name: 'Search Data Pods',
      hotkeys: [{ modifiers: ['Mod', 'Shift'], key: 'd' }],
      editorCallback: (editor, view) => {
        new DataPodsSearchModal(this.app, (result) => {
          editor.replaceSelection(result);
        }).open();
      }
    });
    
    // Add settings
    this.addSettingTab(new DataPodsSettingTab(this.app, this));
  }

  onunload() {
    console.log('Unloading Data Pods Connector...');
  }
}

class DataPodsSearchModal extends FuzzySuggestModal {
  constructor(app, onSelect) {
    super(app);
    this.onSelect = onSelect;
    this.podsPath = `${require('os').homedir()}/.openclaw/data-pods`;
  }

  getItems() {
    // This would connect to the actual pods
    // For now, return sample items
    return [
      { id: '1', title: 'Alex Finn - Anthropic Ban', type: 'pod', content: 'Anthropic banned OpenClaw OAuth...' },
      { id: '2', title: 'Alex Finn - Mac Setup', type: 'pod', content: '$20k Mac Studio setup...' },
      { id: '3', title: 'Khoj Research', type: 'pod', content: 'Khoj is an open-source AI second brain...' },
    ];
  }

  getItemText(item) {
    return item.title;
  }

  renderSuggestion(item, el) {
    el.createEl('div', { text: item.title, cls: 'suggestion-title' });
    el.createEl('small', { text: item.type, cls: 'suggestion-type' });
  }

  onChooseItem(item) {
    this.onSelect(item.content);
  }
}

class DataPodsSettingTab extends PluginSettingTab {
  constructor(app, plugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display() {
    const { containerEl } = this;
    containerEl.empty();
    
    containerEl.createEl('h2', { text: 'Data Pods Settings' });
    
    new Setting(containerEl)
      .setName('Pods Directory')
      .setDesc('Path to your Data Pods folder')
      .addText(text => text
        .setPlaceholder('~/.openclaw/data-pods')
        .setValue(this.plugin.settings.podsPath || '')
        .onChange(value => {
          this.plugin.settings.podsPath = value;
          this.plugin.saveSettings();
        }));
    
    new Setting(containerEl)
      .setName('Default Pod')
      .setDesc('Pod to search by default')
      .addText(text => text
        .setPlaceholder('research')
        .setValue(this.plugin.settings.defaultPod || '')
        .onChange(value => {
          this.plugin.settings.defaultPod = value;
          this.plugin.saveSettings();
        }));
  }
}

module.exports = DataPodsPlugin;
