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
Large OCaml applications rarely consist of OCaml code alone. They typically rely on native C and C++ libraries through the OCaml foreign function interface (FFI), where bindings often manipulate OCaml values directly and depend on the runtime's representation, calling conventions, and memory model. While existing approaches make it possible to compile OCaml programs to WebAssembly, much less is known about porting applications whose native ecosystem is tightly coupled to the OCaml runtime.

This paper presents the experience of porting MOPSA, a static analyzer combining OCaml with LLVM/Clang, GMP, MPFR, Apron, and CamlIDL-generated bindings, to execute entirely inside a web browser. Rather than compiling only the OCaml code, we compile the OCaml bytecode runtime together with the complete native dependency stack into a single statically linked WebAssembly module, preserving the original FFI interfaces and avoiding JavaScript reimplementations of native components.

The port exposed assumptions at several layers of the software stack. Some stem from the OCaml FFI, such as dynamic primitive resolution and direct manipulation of OCaml values from native code. Others originate in native dependencies themselves, including floating-point environment assumptions and architecture-dependent ABI conventions.
\end{abstract}

\section{Introduction}
ouais


\section{Conclusions}\label{conclusions}
There is no longer \LaTeX{} example which was written by \cite{doe}.


\begin{thebibliography}{9}
\bibitem[Doe]{doe} \emph{First and last \LaTeX{} example.},
John Doe 50 B.C. 
\end{thebibliography}

