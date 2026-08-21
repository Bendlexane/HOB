const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);
if (args.length < 6) {
  console.error("Usage: node create_standard_abstract.js <destFolder> <fileName> <title> <conference> <authorsTex> <affiliationsTex>");
  process.exit(1);
}

const [destFolder, fileName, abstractTitle, confName, authorsTex, affiliationsTex] = args;

const vaultRoot = path.resolve(__dirname, '../../');
const resolvedDestFolder = path.isAbsolute(destFolder) ? destFolder : path.join(vaultRoot, destFolder);
const targetPath = path.join(resolvedDestFolder, fileName);

const texContent = `% !TEX program = lualatex
% ========================================================
% Conference Abstract — ${confName}
% Title: ${abstractTitle}
% ========================================================

\\documentclass[11pt]{article}
\\usepackage[a4paper, margin=1in]{geometry}

\\usepackage{libertinus-otf}
\\usepackage{microtype}
\\usepackage{eurosym}

\\usepackage{fancyhdr}

\\usepackage{xcolor}
\\definecolor{accent}{RGB}{58,115,184}
\\definecolor{ink}{RGB}{34,42,53}
\\definecolor{slate}{RGB}{92,103,115}

\\usepackage{hyperref}
\\hypersetup{
    colorlinks=true,
    breaklinks=true,
    urlcolor=accent,
    linkcolor=accent,
    anchorcolor=accent,
    citecolor=accent,
    pdftitle={${abstractTitle.replace(/[&_%$#]/g, '\\$&')}},
}

\\newcommand{\\orcidicon}{\\textsf{[ORCID]}}
\\IfFileExists{academicons.sty}{%
  \\usepackage{academicons}
  \\renewcommand{\\orcidicon}{\\aiOrcid}
}{}

\\setlength{\\parindent}{0pt}
\\setlength{\\parskip}{0.65em}

\\pagestyle{fancy}
\\fancyhf{}
\\renewcommand{\\headrulewidth}{0pt}
\\fancyfoot[C]{\\color{slate}\\small\\thepage}

\\begin{document}
\\color{ink}

\\begin{center}
    {\\LARGE\\bfseries\\color{accent} ${abstractTitle} \\par}
    \\vspace{1.2em}
    {\\large ${authorsTex} \\par}
    \\vspace{0.6em}
    {\\color{slate}\\small
    ${affiliationsTex}
    \\par}
\\end{center}

\\vspace{1.5em}

% ================= Body =================

% Write your abstract text here...

\\end{document}
`;

try {
  // Ensure destination directory exists
  fs.mkdirSync(resolvedDestFolder, { recursive: true });
  fs.writeFileSync(targetPath, texContent, 'utf8');
  console.log(`✅ Standard abstract created at: ${targetPath}`);
} catch (e) {
  console.error(`❌ Failed to create standard abstract file: ${e.message}`);
  process.exit(1);
}
