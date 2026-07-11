---
test: uwu
---

\title{Preserving the OCaml FFI on WebAssembly}
\author{Reda Boudrouss  \\
	Sorbonne University  \\
  contact@rboud.com \\
	}

\date{\today}

\maketitle


\begin{abstract}
Many large OCaml applications do not consist of OCaml code alone. They depend on native C and C++ libraries accessed through the OCaml foreign function interface (FFI), where bindings often manipulate OCaml values directly and rely on the runtime's data representation, calling conventions, and memory model. This tight coupling to the runtime is precisely what makes such applications hard to bring to the browser. How to port them together with their entire native dependency stack remains largely unexplored.

Current OCaml-to-WebAssembly backends compile the OCaml code alone, leaving developers to port native dependencies by hand and to write JavaScript glue code. This paper reports on our experience porting MOPSA, a static analyzer that combines OCaml with LLVM/Clang, GMP, MPFR, Apron, and CamlIDL-generated bindings, to run entirely inside a web browser without any glue code. Instead of compiling only the OCaml code, we compile the OCaml bytecode runtime together with the complete native dependency stack into a single, statically linked WebAssembly module. Linking the runtime supplies the C primitives that the FFI stubs depend on, while the bytecode's external calls are bound through a static primitive table, the mechanism behind OCaml's statically linked (custom) executables, instead of the dynamic loading the runtime normally performs at startup. The fully working runtime is then carried to WebAssembly without any FFI/glue written.
\end{abstract}

\section{Introduction}
ouais


\section{Conclusions}\label{conclusions}
There is no longer \LaTeX{} example which was written by \cite{doe}.


\begin{thebibliography}{9}
\bibitem[Doe]{doe} \emph{First and last \LaTeX{} example.},
John Doe 50 B.C. 
\end{thebibliography}

