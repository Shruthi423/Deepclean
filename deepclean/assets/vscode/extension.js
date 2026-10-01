const vscode = require("vscode");

function run(command, name) {
  const terminal = vscode.window.createTerminal({ name: name || "Deep Clean" });
  terminal.show(true);
  terminal.sendText(command, true);
}

function activate(context) {
  const commands = [
    ["deepclean.analyzeClaude", "deepclean --provider claude --latest --analyze-only"],
    ["deepclean.cleanClaude", "deepclean --provider claude --latest"],
    ["deepclean.analyzeCodex", "deepclean --provider codex --latest --analyze-only"],
    ["deepclean.cleanCodex", "deepclean --provider codex --latest"],
  ];

  for (const [id, command] of commands) {
    context.subscriptions.push(
      vscode.commands.registerCommand(id, () => run(command))
    );
  }
}

function deactivate() {}

module.exports = { activate, deactivate };
