# 📅 Plan de Trabajo — drawio-automation-platform

> Documento de diseño asociado: [DESIGN.md](DESIGN.md)

## Objetivo Principal
**Ordenar automáticamente diagramas de Draw.io a partir de su código XML para lograr un acabado visual apto para entregas profesionales**

---

## Estado Actual (Mayo 30, 2026)

### ✅ Completado (Fase 1-8)
- [x] Investigación de alternativas y gap analysis
- [x] Diseño de arquitectura (FastAPI + ARQ + Docker)
- [x] Implementación de validación corporativa (lxml)
- [x] Sistema de fallback operativo
- [x] Soporte para 7 stencils empresariales
- [x] Dockerfiles optimizados (imagen base de rlespinasse)
- [x] Suite de tests completa (57/57 passing)
- [x] Fork transparente + licenciamiento AGPL-3.0
- [x] Repo Git versionado (v0.1.0)
- [x] Smoke test Docker (stack healthy)
- [x] **Rate limiting** (ya implementado, originalmente planeado para v0.2.0)
- [x] **API Key auth** (Bearer, ya implementado; JWT pendiente)
- [x] **Endpoint `/metrics` Prometheus** (ya implementado)

### ⏳ Pendiente
- [ ] Layout automático real (ELK integration) ← **CRÍTICO para objetivo principal**
- [ ] Documentación de usuario final
- [ ] Integración con orquestador (n8n/Airflow)
- [ ] Despliegue en producción

---

## 🎯 Fases del Plan de Trabajo

### **FASE 9: Layout Automático Real** (2-3 semanas) ⭐ CRÍTICO

> **⚠️ REENMARCADO (29-May-2026):** tras refinar el requerimiento real, esta fase
> deja de ser "solo layout ELK" y pasa a ser una **sub-etapa** de un motor mayor:
> **normalización de drawio crudo (de IA) → drawio C4 válido** para Confluence,
> con el **nivel C4 declarado por el usuario** y un **clasificador C4 pluggable**
> (heurístico + LLM tipo OpenAI para corregir diagramas fuera de estándar).
> El diseño completo y autoritativo vive en
> [C4_NORMALIZER_DESIGN.md](C4_NORMALIZER_DESIGN.md). El layout (ELK) es la etapa 5
> de ese pipeline.

**Objetivo (original):** Implementar layout automático programático usando el motor **ELK (Eclipse Layout Kernel)** para que el XML salga ya ordenado, sin depender del layout manual del navegador.

#### Entregables
1. **Integración de ELK en el worker**
   - Descargar ELK.js (versión compatible con Draw.io)
   - Wrapper Python para invocar ELK vía Node.js subprocess
   - Conversión de mxGraphModel → formato ELK → mxGraphModel ordenado

2. **API de layout configurable**
   - Nuevo campo en request: `layout_algorithm: "elk" | "sugiyama" | "none"`
   - Parámetros: `direction: "TB" | "LR" | "BT" | "RL"`, `spacing: int`

3. **Presets de layout**
   - `enterprise_architecture`: jerárquico, LR, spacing amplio
   - `network_topology`: orgánico, con clustering
   - `flowchart`: Sugiyama, TB, spacing estándar
   - `custom`: parámetros explícitos

#### Criterios de Aceptación
- [ ] XML de entrada desordenado → XML de salida ordenado (coordenadas `<mxGeometry>` recalculadas)
- [ ] Sin cruces de líneas en >90% de casos
- [ ] Performance: <5s para diagramas de 50 nodos
- [ ] Tests unitarios: 20+ tests de layout

#### Riesgos
- ELK.js puede requerir Node.js en el worker (añadir dependencias)
- Conversión de formatos puede perder estilos complejos
- Compatibilidad con todos los stencils no garantizada

> **Nota técnica (validada contra el código, 29-May-2026):** el worker
> (`docker/Dockerfile.worker`, base `rlespinasse/drawio-desktop-headless`)
> **no instala Node.js**: solo añade Python 3.11. Por tanto la opción "ELK.js vía
> subprocess Node" requiere modificar el Dockerfile para instalar Node. Una
> alternativa que evita esa dependencia es un layout jerárquico (Sugiyama) en
> Python puro (p. ej. `grandalf`). El punto de inserción natural es el worker,
> entre la resolución de stencils y el render (`worker/tasks.py::render_drawio`),
> recalculando los `<mxGeometry>` del `mxGraphModel`.

---

### **FASE 10: Documentación de Usuario Final** (1 semana)

**Objetivo:** Documentación completa para que equipos puedan integrar la plataforma en sus flujos de trabajo.

#### Entregables
1. **`docs/USER_GUIDE.md`**
   - Quickstart (5 minutos)
   - API reference con ejemplos cURL/Postman
   - Ejemplos por caso de uso:
     - Generar diagrama AWS desde Terraform state
     - Convertir Mermaid → Draw.io ordenado
     - Batch processing de topologías
   - Troubleshooting común

2. **`docs/COMPLIANCE_GUIDE.md`**
   - Cómo configurar paleta de colores corporativa
   - Cómo obtener licencia ArchiMate
   - Cómo auditar stencils usados

3. **Plantillas de integración**
   - `templates/n8n-workflow.json`: nodo webhook listo para usar
   - `templates/github-action.yml`: CI/CD que genera diagramas
   - `templates/airflow-dag.py`: DAG de Apache Airflow

4. **Videos tutoriales** (opcional)
   - "Primer diagrama en 2 minutos"
   - "Integración con n8n"
   - "Custom stencil loader"

#### Criterios de Aceptación
- [ ] Un usuario nuevo puede generar su primer diagrama en <10 min
- [ ] Todos los ejemplos probados y funcionales
- [ ] Documentación revisada por 2 miembros del equipo

---

### **FASE 11: Integración con Orquestador** (1-2 semanas)

**Objetivo:** Integración nativa con al menos un orquestador de workflows (n8n recomendado).

#### Entregables
1. **n8n custom node** (`n8n-nodes-drawio-automation`)
   - Node type: `drawio.generateDiagram`
   - Inputs: XML payload, format, webhook URL
   - Outputs: S3 URL, compliance report
   - Icon y branding personalizado

2. **Airflow operator** (`DrawioAutomationOperator`)
   ```python
   from airflow.providers.drawio.operators import DrawioAutomationOperator

   generate_arch = DrawioAutomationOperator(
       task_id='generate_architecture',
       xml_template='templates/architecture.xml.j2',
       params={'region': 'us-east-1'},
       export_format='png',
       s3_bucket='diagrams-prod'
   )
   ```

3. **GitHub Action** (`drawio-automation-action`)
   ```yaml
   - name: Generate Architecture Diagram
     uses: your-org/drawio-automation-action@v1
     with:
       xml_file: 'architecture.drawio'
       api_url: ${{ secrets.DRAWIO_API_URL }}
       webhook_url: ${{ secrets.WEBHOOK_URL }}
   ```

4. **Webhook handler example**
   - FastAPI app que recibe callbacks
   - Descarga imagen de S3
   - Envía a Slack/Teams/Email

#### Criterios de Aceptación
- [ ] n8n node publicado en n8n community registry
- [ ] Airflow operator en PyPI
- [ ] GitHub Action en Marketplace
- [ ] Demo end-to-end funcionando

---

### **FASE 12: Despliegue en Producción** (2-3 semanas)

**Objetivo:** Desplegar la plataforma en entorno productivo con alta disponibilidad y observabilidad.

#### Entregables
1. **Infraestructura como Código**
   - **Opción A:** Helm chart para Kubernetes
     - `charts/drawio-automation/`
     - Values para dev/staging/prod
     - HPA (Horizontal Pod Autoscaler) para workers
     - Network policies
   - **Opción B:** Terraform module para AWS ECS
     - `terraform/ecs-deployment/`
     - ALB + WAF + Certificate Manager
     - CloudWatch logs + alarms

2. **Observabilidad**
   - **Métricas:** Prometheus + Grafana
     - `drawio_requests_total` (por status)
     - `drawio_render_duration_seconds`
     - `drawio_queue_depth`
     - `drawio_chromium_crashes_total`
   - **Logs:** ELK stack o CloudWatch Logs Insights
     - JSON estructurado
     - Correlation IDs entre API → Worker
   - **Tracing:** OpenTelemetry → Jaeger
     - Trace completo de request a webhook

3. **Seguridad**
   - API Gateway con rate limiting
   - Secrets management (AWS Secrets Manager / HashiCorp Vault)
   - Network isolation (VPC, security groups)
   - HTTPS obligatorio + mTLS opcional

4. **Disaster Recovery**
   - Backup de Redis (RDB + AOF)
   - S3 versioning + lifecycle policies
   - Multi-AZ deployment
   - Runbook de recovery

5. **Load testing**
   - k6 scripts para simular 1000 requests/min
   - Identificación de bottlenecks
   - Capacidad documentada

#### Criterios de Aceptación
- [ ] Uptime >99.9% (medido por 30 días)
- [ ] P95 render time <30s
- [ ] 0 incidentes de seguridad
- [ ] Alertas configuradas y probadas
- [ ] Runbook documentado

---

### **FASE 13: Optimización y Escalado** (Continuo)

**Objetivo:** Mejorar performance, reducir costos y escalar según demanda.

#### Mejoras Priorizadas

**Performance:**
- [ ] Caché de renders idénticos (hash del XML → S3 URL)
- [ ] Warm pools de workers (containers pre-inicializados)
- [ ] CDN para imágenes exportadas (CloudFront)
- [ ] Compresión de XML en tránsito (gzip)

**Costos:**
- [ ] Spot instances para workers no-críticos
- [ ] Auto-scaling basado en queue depth
- [ ] S3 Intelligent-Tiering para exports
- [ ] Right-sizing de instancias (análisis mensual)

**Features:**
- [ ] Batch API: `POST /api/v1/diagram/batch` (10-100 diagramas)
- [ ] Webhook fan-out (múltiples URLs por request)
- [ ] Streaming de progreso (SSE)
- [ ] Preview thumbnail (PNG 200px) + full resolution

**Developer Experience:**
- [ ] SDK Python oficial (`drawio-automation-python`)
- [ ] SDK TypeScript/Node.js
- [ ] CLI tool (`drawio-cli generate --xml file.drawio`)
- [ ] Plugin para VS Code (preview de XMLs)

---

## 📊 Cronograma Estimado

```
Mayo 2026 (Actual)
├── ✅ v0.1.0 - MVP completo (actual)
│
Junio-Julio 2026 (6 semanas)
├── 🔲 FASE 9: Layout Automático ELK (3 semanas)
├── 🔲 FASE 10: Documentación (1 semana)
└── 🔲 FASE 11: Integración orquestadores (2 semanas)
    └── 🎯 v0.2.0 - Feature Complete
│
Agosto-Septiembre 2026 (4 semanas)
├── 🔲 FASE 12: Producción (3 semanas)
└── 🔲 FASE 13: Optimización inicial (1 semana)
    └── 🎯 v1.0.0 - Production Ready
│
Octubre 2026+ (Continuo)
└── 🔲 FASE 13: Mejoras continuas
    └── 🎯 v1.1.0, v1.2.0, ...
```

---

## 👥 Recursos Necesarios

### Equipo Mínimo
| Rol | Tiempo | Responsabilidad |
|-----|--------|-----------------|
| **Tech Lead** | 20% | Arquitectura, decisiones técnicas, code review |
| **Backend Engineer** | 100% | FASE 9 (ELK), FASE 11 (integraciones) |
| **DevOps Engineer** | 50% | FASE 12 (IaC, observabilidad) |
| **Technical Writer** | 30% | FASE 10 (documentación) |

### Infraestructura (Estimado)
| Entorno | Costo Mensual | Specs |
|---------|---------------|-------|
| **Desarrollo** | $50 | ECS 0.5 vCPU, 1GB RAM |
| **Staging** | $150 | ECS 2 vCPU, 4GB RAM, Redis small |
| **Producción** | $500-1500 | ECS 4 vCPU, 8GB RAM, Redis medium, ALB, WAF |

### Licencias
| Licencia | Costo | Notas |
|----------|-------|-------|
| **ArchiMate** | $2,500/año | Si se usa stencils ArchiMate |
| **AWS Enterprise Support** | $15,000/año | Opcional, para producción crítica |

---

## 🎯 Criterios de Éxito Global

### Objetivo Principal Alcanzado Cuando:
1. ✅ **XML desordenado → XML ordenado automáticamente** (layout ELK funcional)
2. ✅ **Acabado profesional** en >95% de casos (sin cruces, spacing correcto)
3. ✅ **Integración nativa** con al menos 1 orquestador (n8n/Airflow/GitHub Actions)
4. ✅ **Documentación completa** y ejemplos funcionales
5. ✅ **Despliegue en producción** con >99% uptime

### Métricas de Negocio
- **Reducción de tiempo manual:** de 2-4 horas/diagrama a <5 minutos
- **Adopción interna:** >10 equipos usando la plataforma en 6 meses
- **Satisfacción:** NPS >50 de usuarios internos
- **ROI:** Ahorro de >$50,000/año en tiempo de ingenieros

---

## 📞 Próximos Pasos Inmediatos (Esta Semana)

### Prioridad Alta
1. **Decidir enfoque de FASE 9 (Layout ELK):**
   - Opción A: Usar ELK.js vía subprocess Node.js (requiere añadir Node al worker)
   - Opción B: Layout jerárquico en Python puro (`grandalf` / Sugiyama)
   - Opción C: Fork de Draw.io con ELK embebido

2. **Validar conectividad Docker** para smoke tests completos

3. **Configurar ARCHIMATE_LICENSE_KEY** si se usará ArchiMate

### Prioridad Media
4. **Ejecutar `scripts/fetch_stencils.py`** para precachear stencils
5. **Documentar proceso de sync upstream** en FORK.md

### Prioridad Baja
6. **Limpiar rama backup/local-v0.1.0** si no se necesita
7. **Detener contenedores Docker** si no se usan activamente

---

**Fin del Documento**
