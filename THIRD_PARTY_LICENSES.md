# Third-party licenses

HOB bundles eight Obsidian plugins pre-built under `.obsidian/plugins/` so that a
fresh clone works without installing anything. Seven are third-party; one is
HOB's own. Each third-party plugin directory carries its upstream `LICENSE`
file alongside the build it belongs to.

HOB's own code — the vault structure, the theme, `_scripts/`, `_HOME.md` and
the Sky Background plugin — is AGPL-3.0, see [LICENSE](LICENSE). That license
does not extend to the bundled third-party builds listed below, which stay
under their own terms.

| Plugin | Version | License | Upstream |
|---|---|---|---|
| Dataview | 0.5.68 | MIT — © 2021 Michael Brenan | [blacksmithgu/obsidian-dataview](https://github.com/blacksmithgu/obsidian-dataview) |
| Templater | 2.20.5 | **AGPL-3.0** — © SilentVoid13 | [SilentVoid13/Templater](https://github.com/SilentVoid13/Templater) |
| QuickAdd | 2.12.3 | MIT — © 2021 Christian Bager Bach Houmann | [chhoumann/quickadd](https://github.com/chhoumann/quickadd) |
| Full Calendar | 0.10.7 | MIT — © 2022 Davis Haupt | [obsidian-community/obsidian-full-calendar](https://github.com/obsidian-community/obsidian-full-calendar) |
| Make.md | 1.3.5 | MIT — © 2022 JP Cen | [Make-md/makemd](https://github.com/Make-md/makemd) |
| LLM Wiki (HOB fork) | 1.0.3 | MIT — © 2026 Dominique Leca | [Bendlexane/llm-wiki](https://github.com/Bendlexane/llm-wiki), forked from [domleca/llm-wiki](https://github.com/domleca/llm-wiki) |
| Home tab (HOB fork) | 1.3.0 | MIT — © 2023 Lorenzo | [Bendlexane/obsidian-home-tab](https://github.com/Bendlexane/obsidian-home-tab), forked from [olrenso/obsidian-home-tab](https://github.com/olrenso/obsidian-home-tab) |
| Sky Background | 1.0.0 | AGPL-3.0 — part of HOB, see [LICENSE](LICENSE) | this repository |

## Templater and the AGPL

Templater is the one bundled plugin that is **not** MIT. It is licensed under
the GNU Affero General Public License v3.0, a strong copyleft license, and
`.obsidian/plugins/templater-obsidian/LICENSE` carries its full text.

The file shipped here, `.obsidian/plugins/templater-obsidian/main.js`, is the
unmodified official release build of **Templater 2.20.5**. Its corresponding
source is the upstream repository at that tag:

<https://github.com/SilentVoid13/Templater/tree/2.20.5>

HOB's own code is AGPL-3.0, the same license, so no compatibility question
arises here. The bundled MIT plugins remain MIT: aggregating them next to
AGPL code does not relicense them, and MIT terms are satisfied by shipping
each upstream `LICENSE` alongside its build. What the AGPL requires, and what
this file and the per-plugin `LICENSE` exist to satisfy, is that the license
text travels with the binary and that the corresponding source stays
identified and reachable.

If you redistribute HOB, keep `.obsidian/plugins/*/LICENSE` and this file
intact. If you modify Templater's build rather than shipping the official
release, the AGPL requires you to publish your modified source too.

## Templates and the templates you write

The Templater *templates* in `_scripts/templates/` and `_templates/` are HOB's
own work under HOB's AGPL-3.0 license. They are input consumed by Templater at
runtime, not derived from its source.
