# c4norm — motores de layout

Layout intercambiable para el normalizador C4.

- **`elk.py` → `ElkLayout`**: ELK real (Eclipse Layout Kernel) vía `elkjs` sobre
  Node. Ruteo ortogonal que esquiva las cajas. Motor por defecto si Node + elkjs
  están disponibles.
- **`layered.py` → `LayeredLayout`**: fallback en Python puro (sin dependencias).
- **`elk_runner.js`** + **`package.json`**: puente Node (lee grafo ELK por stdin,
  devuelve el layout por stdout).

## Instalación del puente ELK

```bash
cd c4norm/layout
npm install        # instala elkjs (node_modules está gitignored)
```

Requiere Node.js (cualquier LTS reciente). El binario se localiza por, en orden:
`C4NORM_NODE_BIN` → `node` en PATH → instalación winget portable (Windows).

## Selección de motor

```bash
# automático (ELK si está; si no, fallback)
python -m c4norm entrada.drawio.xml --level 2 -o salida.xml

# forzar uno u otro
C4NORM_LAYOUT=elk      python -m c4norm ...   # falla si ELK no está
C4NORM_LAYOUT=layered  python -m c4norm ...   # Python puro
```

## Docker / enterprise

La imagen donde corra el normalizador debe instalar Node.js y ejecutar
`npm install` en este directorio. Sin Node, el sistema usa el fallback Python sin
romperse.
