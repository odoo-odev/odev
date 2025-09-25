/** @type {import('prettier').Config} */

const config = {
    proseWrap: "always",
    semi: true,
    tabWidth: 2,
    useTabs: false,
    printWidth: 120,
    bracketSpacing: false,
    bracketSameLine: true,
    singleAttributePerLine: false,
    trailingComma: "es5",

    plugins: ["@prettier/plugin-xml"],
    xmlQuoteAttributes: "double",
    xmlSelfClosingSpace: false,
    xmlWhitespaceSensitivity: "preserve",
};

module.exports = config;
