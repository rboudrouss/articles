---
title: "Compiling FFI-heavy OCaml to WebAssembly"
subtitle: "An Experience Report on MOPSA"
author: Reda Boudrouss
institute: Sorbonne University
date: OCaml Workshop 2026 · August 24, Paris
lang: en
aspectratio: 169
theme: metropolis
themeoptions:
  - numbering=none
  - progressbar=frametitle
  - sectionpage=none
header-includes:
  - \usepackage{graphicx}
  - \metroset{block=fill}
  - \setmonofont[Scale=0.85]{DejaVu Sans Mono}
  # line highlighting inside fancyvrb Verbatim blocks (needs {.fragile} on the slide)
  - \usepackage{fancyvrb}
  - \newcommand{\hlbad}[1]{\begingroup\setlength{\fboxsep}{1pt}\colorbox{red!15}{#1}\endgroup}
  - \newcommand{\hlgood}[1]{\begingroup\setlength{\fboxsep}{1pt}\colorbox{green!20}{#1}\endgroup}
  # metropolis's [standout] opens a group whose \endgroup never runs under
  # beamer's ignorenonframetext (pandoc's template), leaking the dark palette,
  # font and centering into every following frame. Close it ourselves.
  - \makeatletter\newcommand{\fixstandoutleak}{\ifbool{metropolis@standout}{\endgroup\boolfalse{metropolis@standout}}{}}\makeatother
  - \BeforeBeginEnvironment{frame}{\fixstandoutleak}
  - \pretocmd{\section}{\fixstandoutleak}{}{}
  # Décommente si Fira Sans n'est pas installée :
  # - \setsansfont{Latin Modern Sans}
---
