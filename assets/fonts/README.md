# Label Font

`NotoSansSC.ttf` is a static weight-400 instance of Google Fonts' Noto Sans SC variable font. It is bundled for reproducible Chinese label printing and embedded into PDFs as a glyph subset.

Source: https://github.com/google/fonts/tree/main/ofl/notosanssc

Downloaded variable-font SHA-256: `a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da`.

Bundled static-font SHA-256: `4f5c4033f806521fa348f2cf311357d99a686e5757424380cda6e7a973b6cd42`.

License: [SIL Open Font License 1.1](OFL.txt). The font license applies to this asset, independently of the repository code.

The instance was generated with fontTools 4.60.2:

```python
font = TTFont("NotoSansSC[wght].ttf")
font = instantiateVariableFont(font, {"wght": 400}, inplace=True)
font.save("NotoSansSC.ttf")
```

Do not subset the bundled font to the current inventory names: future objects may use other Chinese characters. The PDF generator subsets each output automatically.
