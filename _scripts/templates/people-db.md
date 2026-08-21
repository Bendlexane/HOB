<%*
// Shared helpers (cache-busted so edits to the lib take effect immediately).
const _lp = `${app.vault.adapter.basePath}/_scripts/lib/templater-utils.js`;
try { delete require.cache[_lp]; } catch (e) {}
const U = require(_lp);

// ─── 1. READ PEOPLE DB ─────────────────────────────────────────────────────
const peopleDbPath = U.PEOPLE_DB_PATH;

// ─── 2. MODE SELECTION ─────────────────────────────────────────────────────
let mode;
let presetVal;
if (window._actionPreset) {
    mode = window._actionPreset.mode;
    presetVal = window._actionPreset.presetVal;
    window._actionPreset = null; // consume
} else {
    mode = await tp.system.suggester(
        ["Add new collaborator", "Edit existing collaborator"],
        ["add", "edit"]
    );
}
if (!mode) return;

const { file, data } = await U.readPeopleDb();

// ─── 3. ADD MODE ───────────────────────────────────────────────────────────
if (mode === "add") {
    const rawName = await tp.system.prompt("Display name (format: Surname, Given Names)", "");
    if (!rawName) return;
    const name = U.normalizeSpaces(rawName);

    const surnameFirst = name.includes(",") ? name : `${name},`;
    const [surnameRaw, givenRaw = ""] = surnameFirst.split(",");
    const surname = U.titleCase(U.normalizeSpaces(surnameRaw));
    const given_names = U.titleCase(U.normalizeSpaces(givenRaw));

    const aliasesRaw = await tp.system.prompt("Aliases (semicolon-separated, e.g. 'Smith, T; Thomas Smith')", "");
    const aliases = aliasesRaw
        ? aliasesRaw.split(";").map(s => U.normalizeSpaces(s)).filter(Boolean)
        : [];

    const affiliationsRaw = await tp.system.prompt("Affiliations (semicolon-separated)", "");
    const affiliations = affiliationsRaw
        ? affiliationsRaw.split(";").map(s => U.normalizeSpaces(s)).filter(Boolean)
        : [];

    const orcid = await tp.system.prompt("ORCID (optional)", "");
    const email = await tp.system.prompt("Email (optional)", "");
    const notes = await tp.system.prompt("Notes (optional)", "");

    const slugBase = surname
        ? `${U.generateSlug(surname)}-${U.generateSlug(given_names)}`.replace(/-+$/g, "")
        : U.generateSlug(name);
    const slug = slugBase || U.generateSlug(name);
    const rand = Math.random().toString(16).slice(2, 6);
    const canonicalSurname = surname.toLowerCase().trim();
    const canonicalGiven = given_names.toLowerCase().trim();

    // Check for duplicate slug
    const hasSlug = data.people.some(p => p.slug === slug);
    const finalSlug = hasSlug ? `${slug}-${rand}` : slug;

    const person = {
        id: `${finalSlug}-${rand}`,
        slug: finalSlug,
        display_name: name,
        surname,
        given_names,
        canonical_name: canonicalGiven ? `${canonicalSurname}|${canonicalGiven}` : canonicalSurname,
        aliases,
        affiliations,
        orcid: orcid || null,
        email: email || null,
        notes: notes || ""
    };

    data.people.push(person);
    await U.savePeopleDb(file, data);
    new Notice(`✅ Added collaborator: ${name} (id: ${person.id})`);
    tR += `Added **${name}** ([[${peopleDbPath}|people DB]]).\n`;
    return;
}

// ─── 4. EDIT MODE ──────────────────────────────────────────────────────────
if (mode === "edit") {
    if (!data.people.length) {
        new Notice("❌ People DB is empty — nothing to edit.");
        return;
    }

    let choice;
    if (presetVal) {
        choice = presetVal;
    } else {
        const labels = [];
        const values = [];
        const seen = new Set();
        for (const p of data.people) {
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
        choice = await tp.system.suggester(labels, values);
    }
    if (!choice) return;

    const idx = data.people.findIndex(p => p.id === choice);
    if (idx === -1) return;
    const p = data.people[idx];
    const oldName = p.display_name; // capture before any edit

    const fields = [
        { key: "display_name", label: "Display name", current: p.display_name },
        { key: "surname", label: "Surname", current: p.surname },
        { key: "given_names", label: "Given names", current: p.given_names },
        { key: "aliases", label: "Aliases (semicolon-separated)", current: (p.aliases || []).join("; ") },
        { key: "affiliations", label: "Affiliations (semicolon-separated)", current: (p.affiliations || []).join("; ") },
        { key: "orcid", label: "ORCID", current: p.orcid || "" },
        { key: "email", label: "Email", current: p.email || "" },
        { key: "notes", label: "Notes", current: p.notes || "" }
    ];

    const fieldLabels = fields.map(f => `${f.key}: ${f.current}`);
    const fieldKeys = fields.map(f => f.key);
    const chosenField = await tp.system.suggester(fieldLabels, fieldKeys);
    if (!chosenField) {
        new Notice("❌ No field selected — edit cancelled.");
        return;
    }

    const field = fields.find(f => f.key === chosenField);
    const newValue = await tp.system.prompt(`Edit ${field.label}`, field.current);
    if (newValue === null) {
        new Notice("❌ Edit cancelled.");
        return;
    }

    if (chosenField === "aliases" || chosenField === "affiliations") {
        p[chosenField] = newValue
            ? newValue.split(";").map(s => U.normalizeSpaces(s)).filter(Boolean)
            : [];
    } else if (chosenField === "orcid" || chosenField === "email") {
        p[chosenField] = newValue || null;
    } else {
        p[chosenField] = U.normalizeSpaces(newValue) || p[chosenField];
    }

    // Recompute derived fields if name changed
    if (chosenField === "display_name" || chosenField === "surname" || chosenField === "given_names") {
        const surname = U.titleCase(U.normalizeSpaces(p.surname));
        const given_names = U.titleCase(U.normalizeSpaces(p.given_names));
        p.surname = surname;
        p.given_names = given_names;
        p.canonical_name = given_names
            ? `${surname.toLowerCase().trim()}|${given_names.toLowerCase().trim()}`
            : surname.toLowerCase().trim();
        p.display_name = given_names ? `${surname}, ${given_names}` : surname;
        const newSlug = `${U.generateSlug(surname)}-${U.generateSlug(given_names)}`.replace(/-+$/g, "") || U.generateSlug(p.display_name);
        p.slug = newSlug;
        p.id = `${newSlug}-${Math.random().toString(16).slice(2, 6)}`;
    }

    await U.savePeopleDb(file, data);

    // ─── 5. PROPAGATE TO _project.md FILES ─────────────────────────────────
    // Only propagate when email, affiliations, or name changed — not for
    // aliases/orcid/notes which are not shown in project coauthor tables.
    const propagateFields = new Set(["display_name", "surname", "given_names", "email", "affiliations"]);

    if (propagateFields.has(chosenField)) {
        function escRe(s) {
            return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        }

        const newName     = p.display_name;
        const newAffil    = (p.affiliations?.[0] || "—").replace(/\|/g, "\\|");
        const newEmail    = (p.email || "—").replace(/\|/g, "\\|");
        const newRow      = `| ${newName.replace(/\|/g, "\\|")} | ${newAffil} | ${newEmail} |`;

        // Collect all name forms for matching: canonical display_name first, then aliases.
        // This handles cases where projects use abbreviated names (e.g. "Smith, J.")
        // while the DB stores the full name (e.g. "Smith, John").
        const searchNames = [oldName, ...(p.aliases || [])].filter(Boolean);

        const projectFiles = app.vault.getMarkdownFiles()
            .filter(f => f.path.startsWith("01_PROJECTS/") && f.name === "_project.md");

        let nUpdated = 0;
        for (const pf of projectFiles) {
            let content = await app.vault.read(pf);

            // Check if any form of the name appears in the content
            const matchedSearchName = searchNames.find(n => content.includes(n));
            if (!matchedSearchName) continue;

            let changed = false;

            // 5a. Update coauthors table row (try each name form until one matches)
            for (const candidate of searchNames) {
                const rowRe = new RegExp(`\\|\\s*${escRe(candidate)}\\s*\\|[^\\n]+`, "g");
                const after = content.replace(rowRe, newRow);
                if (after !== content) {
                    content = after;
                    changed = true;
                    break;
                }
            }

            // 5b. Update frontmatter coauthors list if name changed
            if (newName !== oldName) {
                for (const candidate of searchNames) {
                    // Quoted YAML: `  - "Smith, J."`
                    const fmReQ = new RegExp(`(  - )"${escRe(candidate)}"`, "g");
                    const afterFmQ = content.replace(fmReQ, `$1"${newName}"`);
                    if (afterFmQ !== content) { content = afterFmQ; changed = true; break; }

                    // Unquoted YAML: `  - Smith, J.`
                    const fmReU = new RegExp(`(  - )${escRe(candidate)}(\\r?\\n)`, "g");
                    const afterFmU = content.replace(fmReU, `$1${newName}$2`);
                    if (afterFmU !== content) { content = afterFmU; changed = true; break; }
                }
            }

            // 5c. lead_author / senior_author scalar fields
            if (newName !== oldName) {
                for (const candidate of searchNames) {
                    let beforeReplace = content;
                    // Quoted: `lead_author: "Smith, J."`
                    content = content.replace(
                        new RegExp(`(lead_author:\\s*)"${escRe(candidate)}"`, "g"),
                        `$1"${newName}"`
                    );
                    content = content.replace(
                        new RegExp(`(senior_author:\\s*)"${escRe(candidate)}"`, "g"),
                        `$1"${newName}"`
                    );
                    // Unquoted: `lead_author: Smith, J.`
                    content = content.replace(
                        new RegExp(`(lead_author:\\s*)${escRe(candidate)}(\\r?\\n|\\r)`, "g"),
                        `$1${newName}$2`
                    );
                    content = content.replace(
                        new RegExp(`(senior_author:\\s*)${escRe(candidate)}(\\r?\\n|\\r)`, "g"),
                        `$1${newName}$2`
                    );
                    if (content !== beforeReplace) { changed = true; break; }
                }
            }

            if (changed) {
                await app.vault.modify(pf, content);
                nUpdated++;
            }
        }

        const propagateNote = nUpdated > 0
            ? ` [Auto-sync: updated ${nUpdated} project file${nUpdated > 1 ? "s" : ""}]`
            : " [Auto-sync: checked projects, no updates needed]";

        new Notice(`✅ Edited ${field.key} for ${p.display_name}${propagateNote}`);
        tR += `Edited **${field.key}** for **${p.display_name}** ([[${peopleDbPath}|people DB]])${propagateNote}\n`;
    } else {
        new Notice(`✅ Edited ${field.key} for ${p.display_name}`);
        tR += `Edited **${field.key}** for **${p.display_name}** ([[${peopleDbPath}|people DB]]).\n`;
    }
}
%>
