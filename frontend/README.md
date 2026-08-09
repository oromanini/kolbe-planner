# Kolbe Planner — frontend

React 19 + Vite + Tailwind CSS, com componentes shadcn/ui em `src/components/ui`.

## Scripts

Na pasta `frontend/`:

| Comando | O que faz |
| --- | --- |
| `npm run dev` | Sobe o servidor de desenvolvimento em <http://localhost:3000> com hot reload. |
| `npm start` | Apelido de `npm run dev`. |
| `npm run build` | Gera a build de produção em `dist/`. |
| `npm run preview` | Serve localmente o conteúdo de `dist/` para conferir a build. |
| `npm run lint` | Roda o ESLint (config flat em `eslint.config.js`). |

## Variáveis de ambiente

A URL do backend é injetada em tempo de build. Crie um `.env.local` para
desenvolvimento:

```
VITE_BACKEND_URL=http://localhost:8000
```

`REACT_APP_BACKEND_URL` continua sendo aceito como fallback, para não quebrar
pipelines anteriores à migração para o Vite. A resolução fica centralizada em
`src/lib/env.js`; se nenhuma das duas estiver definida, as chamadas ficam
relativas à origem que serve a aplicação.

Só variáveis com os prefixos `VITE_` e `REACT_APP_` chegam ao código do
navegador — ver `envPrefix` em `vite.config.js`.

## Estrutura

- `index.html` — entrada da aplicação (na raiz do projeto, como o Vite espera).
- `src/main.jsx` — ponto de montagem do React.
- `public/` — arquivos estáticos servidos como estão na raiz (`/kp-logo.png`).
- `@/` — alias para `src/` (configurado no `vite.config.js` e no `jsconfig.json`).

Arquivos com JSX usam a extensão `.jsx`.
