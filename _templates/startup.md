<%*
// HOB Startup Script — Registers global behaviors on Obsidian load

// Clean up previous listener if any
if (window._hobLogoClickListener) {
  document.removeEventListener('click', window._hobLogoClickListener, true);
}

window._hobLogoClickListener = (e) => {
  // The logo is a ::before pseudo-element on workspace-leaf-content panels.
  // Pseudo-elements don't receive click events — the click lands on the
  // parent element. We detect it by checking the selector + click position.

  // Find the closest leaf-content that holds a sidebar file tree
  const leaf = e.target.closest(
    '.workspace-leaf-content[data-type="mk-path-view"], ' +
    '.workspace-leaf-content[data-type="file-explorer"]'
  );

  // Also check the old make.md container (some layouts still use it)
  const mkContainer = e.target.closest('.mk-main-menu-container');

  const target = leaf || mkContainer;
  if (!target) return;

  const rect = target.getBoundingClientRect();
  const clickY = e.clientY - rect.top;

  // The logo pseudo-element: margin-top 10px + height 120px + margin-bottom 14px = 144px
  if (clickY >= 0 && clickY <= 150) {
    e.preventDefault();
    e.stopPropagation();

    try {
      if (app.commands.commands['homepage:open-homepage']) {
        app.commands.executeCommandById('homepage:open-homepage');
      } else {
        app.workspace.openLinkText("_HOME.md", "", false);
      }
    } catch (err) {
      app.workspace.openLinkText("_HOME.md", "", false);
    }
  }
};

document.addEventListener('click', window._hobLogoClickListener, true);
console.log("HOB: Global logo click listener registered (targets workspace-leaf-content + mk-main-menu-container, click range 0-150px).");
%>
