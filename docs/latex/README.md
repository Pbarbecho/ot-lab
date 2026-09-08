# Guía LaTeX — Laboratorio de redes industriales en Docker

Compilar (2–3 pasadas para índice y referencias):

    pdflatex guia.tex && pdflatex guia.tex && pdflatex guia.tex
    # o
    latexmk -pdf guia.tex

Overleaf: subir esta carpeta comprimida en .zip; compilador pdfLaTeX.

Estructura:
- guia.tex            preámbulo (paquetes, colores, estilos TikZ, listings) e \input de capítulos
- capitulos/          un archivo por capítulo (00-portada … 08-problemas, A-anexos)
- figuras/            PNG (fig1–fig6) sin pie embebido; los demás diagramas son TikZ en los .tex
- src/                copias de docker-compose.yml, server.json, server.py, Dockerfile, mosquitto.conf
                      (se incluyen con \lstinputlisting; actualizar si cambian los originales)

Paquetes requeridos: babel (spanish), tikz, tcolorbox, listings, booktabs, tabularx, longtable,
enumitem, fancyhdr, hyperref, xurl, hyphenat, microtype, lmodern, caption, float.
