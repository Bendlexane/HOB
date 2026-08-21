<%*
const peopleDbPath = "04_PEOPLE/collaborators/_people-db.json";

async function readPeopleDb() {
    let file = app.vault.getAbstractFileByPath(peopleDbPath);
    if (!file) return [];
    const raw = await app.vault.read(file);
    try {
        const parsed = JSON.parse(raw);
        return parsed.people || [];
    } catch (e) {
        return [];
    }
}

const people = await readPeopleDb();
if (!people.length) {
    new Notice("❌ People DB is empty or missing.");
    return;
}

// ─── 1. SELECT PERSON ──────────────────────────────────────────────────────
let choice;
if (window._actionPreset && window._actionPreset.presetVal) {
    choice = window._actionPreset.presetVal;
    window._actionPreset = null; // consume
} else {
    const labels = [];
    const values = [];
    const seen = new Set();
    for (const p of people) {
        const forms = [p.display_name, ...(p.aliases || [])];
        for (const form of forms) {
            const key = form?.toLowerCase().trim();
            if (key && !seen.has(key)) {
                seen.add(key);
                labels.push(form);
                values.push(p.id);
            }
        }
    }
    choice = await tp.system.suggester(labels, values, false, "Select collaborator to view");
}
if (!choice) return;

const person = people.find(p => p.id === choice);
if (!person) return;

// ─── 2. RENDER CARD WITH RESTORE FUNCTION FOR RE-RENDERS ────────────────────
const slotExists = document.querySelector('.home-banner-action-suggester') !== null;

if (slotExists) {
    const runRestore = () => {
        const slot = document.querySelector('.home-banner-action-suggester');
        if (!slot) return;
        slot.empty();
        slot.style.display = 'block';

        const card = slot.createDiv();
        card.style.cssText = 'background:var(--vault-glass-card);backdrop-filter:var(--vault-blur);-webkit-backdrop-filter:var(--vault-blur);border:0.5px solid var(--vault-glass-border);color:var(--text-normal);border-radius:16px;padding:1.4rem;box-shadow:0 10px 34px rgba(0,0,0,0.22);display:flex;flex-direction:column;gap:0.9rem;position:relative;';

        // Header row
        const head = card.createDiv();
        head.style.cssText = 'display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid rgba(255,255,255,0.08);padding-bottom:0.6rem;';
        
        const titleEl = head.createSpan({text: '👤 Collaborator Profile'});
        titleEl.style.cssText = 'font-weight:700;font-size:1.15rem;color:var(--text-accent);';

        const closeBtn = head.createEl('button', {text: '×'});
        closeBtn.style.cssText = 'border:none;background:transparent;color:var(--text-muted);font-size:1.6rem;cursor:pointer;line-height:1;padding:0;transition:color 0.15s;';
        closeBtn.addEventListener('mouseenter', () => closeBtn.style.color = 'var(--text-normal)');
        closeBtn.addEventListener('mouseleave', () => closeBtn.style.color = 'var(--text-muted)');
        
        const dismiss = () => {
            slot.empty();
            slot.style.display = 'none';
            window._activeActionState = null;
            window._activeActionStateRestore = null;
        };
        closeBtn.addEventListener('click', dismiss);

        // Name Section
        const nameSection = card.createDiv();
        nameSection.style.cssText = 'display:flex;flex-direction:column;gap:0.25rem;';
        const dispName = nameSection.createDiv({text: person.display_name});
        dispName.style.cssText = 'font-size:1.6rem;font-weight:800;letter-spacing:-0.01em;';
        
        if (person.surname && person.given_names) {
            const subName = nameSection.createDiv({text: `${person.given_names} ${person.surname}`});
            subName.style.cssText = 'font-size:0.9rem;color:var(--text-muted);';
        }

        // Info Grid
        const infoGrid = card.createDiv();
        infoGrid.style.cssText = 'display:flex;flex-direction:column;gap:0.6rem;margin-top:0.2rem;';

        const addRow = (icon, label, value, isLink = false, linkHref = '') => {
            if (!value) return;
            const row = infoGrid.createDiv();
            row.style.cssText = 'display:flex;align-items:start;gap:0.75rem;font-size:0.9rem;line-height:1.4;';
            
            const iconSpan = row.createSpan({text: icon});
            iconSpan.style.cssText = 'font-size:1.05rem;opacity:0.8;flex-shrink:0;';
            
            const contentBox = row.createDiv();
            contentBox.style.cssText = 'display:flex;flex-direction:column;';
            
            const labelEl = contentBox.createSpan({text: label});
            labelEl.style.cssText = 'font-size:0.7rem;text-transform:uppercase;color:var(--text-faint);letter-spacing:0.03em;font-weight:600;';
            
            if (isLink && linkHref) {
                const a = contentBox.createEl('a', {text: value, href: linkHref});
                a.style.cssText = 'color:var(--text-accent);text-decoration:none;font-weight:500;';
                a.setAttribute('target', '_blank');
            } else {
                const valSpan = contentBox.createSpan({text: value});
                valSpan.style.cssText = 'color:var(--text-normal);font-weight:500;';
            }
        };

        // Affiliations
        if (person.affiliations && person.affiliations.length) {
            addRow('🏢', 'Affiliations', person.affiliations.join('; '));
        } else {
            addRow('🏢', 'Affiliations', '—');
        }

        // Email
        if (person.email) {
            addRow('✉️', 'Email', person.email, true, `mailto:${person.email}`);
        }

        // ORCID
        if (person.orcid) {
            const orcidUrl = person.orcid.startsWith('http') ? person.orcid : `https://orcid.org/${person.orcid}`;
            addRow('🆔', 'ORCID', person.orcid, true, orcidUrl);
        }

        // Aliases
        if (person.aliases && person.aliases.length) {
            addRow('👤', 'Aliases', person.aliases.join('; '));
        }

        // Notes
        if (person.notes) {
            addRow('📝', 'Notes', person.notes);
        }

        // Footer actions
        const footer = card.createDiv();
        footer.style.cssText = 'display:flex;justify-content:flex-end;gap:0.6rem;margin-top:0.4rem;border-top:1px solid rgba(255,255,255,0.08);padding-top:0.8rem;';
        
        const editBtn = footer.createEl('button', {text: '✏️ Edit Collaborator'});
        editBtn.style.cssText = 'border:none;background:var(--interactive-accent);color:var(--text-on-accent);font-size:0.8rem;padding:0.45rem 1rem;border-radius:8px;cursor:pointer;font-weight:600;transition:opacity 0.15s;';
        editBtn.addEventListener('mouseenter', () => editBtn.style.opacity = '0.9');
        editBtn.addEventListener('mouseleave', () => editBtn.style.opacity = '1');
        editBtn.addEventListener('click', () => {
            dismiss();
            window._actionPreset = { file: "people-db.md", mode: "edit", presetVal: person.id };
            app.commands.executeCommandById('templater-obsidian:_templates/actions.md');
        });

        const closeCardBtn = footer.createEl('button', {text: 'Close'});
        closeCardBtn.style.cssText = 'border:1px solid var(--vault-glass-border);background:transparent;color:var(--text-normal);font-size:0.8rem;padding:0.45rem 1rem;border-radius:8px;cursor:pointer;font-weight:600;transition:background 0.15s;';
        closeCardBtn.addEventListener('mouseenter', () => closeCardBtn.style.background = 'rgba(255,255,255,0.05)');
        closeCardBtn.addEventListener('mouseleave', () => closeCardBtn.style.background = 'transparent');
        closeCardBtn.addEventListener('click', dismiss);
    };

    window._activeActionState = {
        type: 'person-card',
        title: 'Collaborator Info',
        person: person,
        onCancel: () => {
            window._activeActionState = null;
            window._activeActionStateRestore = null;
        }
    };
    window._activeActionStateRestore = runRestore;
    runRestore();

} else {
    // Fallback: view in a Notice
    let info = `👤 ${person.display_name}\n`;
    if (person.affiliations && person.affiliations.length) info += `🏢 Affiliations: ${person.affiliations.join('; ')}\n`;
    if (person.email) info += `✉️ Email: ${person.email}\n`;
    if (person.orcid) info += `🆔 ORCID: ${person.orcid}\n`;
    if (person.notes) info += `📝 Notes: ${person.notes}\n`;
    new Notice(info, 10000);
}
%>
