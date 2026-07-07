"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card"
import { Progress } from "./ui/progress"
import { Badge } from "./ui/badge"
import {
  Server,
  Cpu,
  MemoryStick,
  Thermometer,
  Box,
  Boxes,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Network,
} from "lucide-react"
import { fetchApi } from "../lib/api-config"

// ── Types (mirror scripts/cluster_manager.aggregate_overview) ────────────
interface ClusterNode {
  name: string
  id?: number
  ip?: string
  local: boolean
  online: boolean
  reachable: boolean
  error?: string | null
  cpu_usage?: number
  memory_usage?: number
  memory_total?: number
  memory_used?: number
  temperature?: number | null
  uptime?: string
  load_average?: number[] | null
  cpu_cores?: number
  cpu_threads?: number
  proxmox_version?: string
  kernel_version?: string
  vms?: { running: number; total: number }
  lxc?: { running: number; total: number }
}

interface ClusterOverviewData {
  cluster: {
    name: string | null
    in_cluster: boolean
    quorate: boolean
    nodes_total: number
    nodes_online: number
    local_node: string
  }
  totals: {
    cpu_usage_avg: number
    cpu_cores: number
    cpu_threads: number
    memory_total: number
    memory_used: number
    memory_usage: number
    vms: { running: number; total: number }
    lxc: { running: number; total: number }
  }
  nodes: ClusterNode[]
}

const POLL_MS = 5000

function usageColor(pct: number): string {
  if (pct >= 90) return "[&>div]:bg-red-500"
  if (pct >= 75) return "[&>div]:bg-amber-500"
  return "[&>div]:bg-blue-500"
}

function TotalCard({
  icon,
  label,
  value,
  sub,
}: {
  icon: React.ReactNode
  label: string
  value: string
  sub?: string
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-3">
          <div className="text-blue-500">{icon}</div>
          <div className="min-w-0">
            <p className="text-xs text-muted-foreground truncate">{label}</p>
            <p className="text-xl font-semibold leading-tight">{value}</p>
            {sub && <p className="text-xs text-muted-foreground truncate">{sub}</p>}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function NodeCard({ node }: { node: ClusterNode }) {
  const down = !node.reachable
  const cpu = Math.round(node.cpu_usage ?? 0)
  const mem = Math.round(node.memory_usage ?? 0)

  return (
    <Card className={down ? "opacity-60" : ""}>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center justify-between gap-2 text-base">
          <span className="flex items-center gap-2 min-w-0">
            <Server className="h-4 w-4 shrink-0 text-blue-500" />
            <span className="truncate">{node.name}</span>
            {node.local && (
              <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                this node
              </Badge>
            )}
          </span>
          {node.reachable ? (
            <Badge className="gap-1 bg-green-500/15 text-green-600 hover:bg-green-500/15">
              <CheckCircle2 className="h-3 w-3" /> online
            </Badge>
          ) : (
            <Badge className="gap-1 bg-red-500/15 text-red-600 hover:bg-red-500/15">
              <XCircle className="h-3 w-3" /> {node.online ? "unreachable" : "offline"}
            </Badge>
          )}
        </CardTitle>
      </CardHeader>

      {node.reachable ? (
        <CardContent className="space-y-3">
          {/* CPU */}
          <div>
            <div className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-1.5 text-muted-foreground">
                <Cpu className="h-3.5 w-3.5" /> CPU
              </span>
              <span className="font-medium">{cpu}%</span>
            </div>
            <Progress value={cpu} className={`mt-1 h-2 ${usageColor(cpu)}`} />
          </div>

          {/* Memory */}
          <div>
            <div className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-1.5 text-muted-foreground">
                <MemoryStick className="h-3.5 w-3.5" /> Memory
              </span>
              <span className="font-medium">
                {(node.memory_used ?? 0).toFixed(1)}/{(node.memory_total ?? 0).toFixed(1)} GB
              </span>
            </div>
            <Progress value={mem} className={`mt-1 h-2 ${usageColor(mem)}`} />
          </div>

          {/* Facts row */}
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground pt-1">
            {node.temperature != null && (
              <span className="flex items-center gap-1">
                <Thermometer className="h-3 w-3" />
                {node.temperature}°C
              </span>
            )}
            <span className="flex items-center gap-1">
              <Cpu className="h-3 w-3" />
              {node.cpu_cores ?? "?"}c / {node.cpu_threads ?? "?"}t
            </span>
            {node.vms && (
              <span className="flex items-center gap-1">
                <Box className="h-3 w-3" />
                {node.vms.running}/{node.vms.total} VM
              </span>
            )}
            {node.lxc && (
              <span className="flex items-center gap-1">
                <Boxes className="h-3 w-3" />
                {node.lxc.running}/{node.lxc.total} LXC
              </span>
            )}
          </div>

          {(node.proxmox_version || node.uptime) && (
            <div className="text-[11px] text-muted-foreground border-t border-border pt-2">
              {node.proxmox_version && <span>PVE {node.proxmox_version}</span>}
              {node.proxmox_version && node.uptime && <span> · </span>}
              {node.uptime && <span>up {node.uptime}</span>}
            </div>
          )}
        </CardContent>
      ) : (
        <CardContent>
          <p className="text-sm text-muted-foreground flex items-center gap-2">
            <AlertCircle className="h-4 w-4" />
            {node.error ? `Not reachable: ${node.error}` : "Node not reachable"}
          </p>
          {node.ip && (
            <p className="text-xs text-muted-foreground mt-1">{node.ip}</p>
          )}
        </CardContent>
      )}
    </Card>
  )
}

export function ClusterOverview() {
  const [data, setData] = useState<ClusterOverviewData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true

    const load = async () => {
      try {
        const res = await fetchApi<ClusterOverviewData>("/api/cluster/overview")
        if (!alive) return
        setData(res)
        setError(null)
      } catch (e) {
        if (!alive) return
        setError(e instanceof Error ? e.message : "Failed to load cluster overview")
      } finally {
        if (alive) setLoading(false)
      }
    }

    load()
    const interval = setInterval(load, POLL_MS)
    return () => {
      alive = false
      clearInterval(interval)
    }
  }, [])

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        <Server className="h-5 w-5 animate-pulse mr-2" /> Loading cluster…
      </div>
    )
  }

  if (error && !data) {
    return (
      <Card>
        <CardContent className="py-10 text-center">
          <AlertCircle className="h-6 w-6 mx-auto text-red-500 mb-2" />
          <p className="text-sm text-muted-foreground">{error}</p>
        </CardContent>
      </Card>
    )
  }

  if (!data) return null

  const { cluster, totals, nodes } = data

  // Standalone node (not part of a cluster) — explain instead of empty view.
  if (!cluster.in_cluster) {
    return (
      <Card>
        <CardContent className="py-10 text-center space-y-2">
          <Network className="h-7 w-7 mx-auto text-muted-foreground" />
          <p className="font-medium">This node is not part of a Proxmox cluster</p>
          <p className="text-sm text-muted-foreground">
            The cluster overview aggregates every node automatically once{" "}
            <span className="font-mono">{cluster.local_node}</span> joins a cluster —
            no configuration needed.
          </p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-4 md:space-y-6">
      {/* Cluster header */}
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Network className="h-5 w-5 text-blue-500" />
          {cluster.name || "Cluster"}
        </h2>
        {cluster.quorate ? (
          <Badge className="bg-green-500/15 text-green-600 hover:bg-green-500/15">
            quorate
          </Badge>
        ) : (
          <Badge className="bg-red-500/15 text-red-600 hover:bg-red-500/15">
            no quorum
          </Badge>
        )}
        <Badge variant="secondary">
          {cluster.nodes_online}/{cluster.nodes_total} nodes online
        </Badge>
      </div>

      {/* Cluster totals */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
        <TotalCard
          icon={<Cpu className="h-6 w-6" />}
          label="Cluster CPU (avg)"
          value={`${totals.cpu_usage_avg}%`}
          sub={`${totals.cpu_cores} cores · ${totals.cpu_threads} threads`}
        />
        <TotalCard
          icon={<MemoryStick className="h-6 w-6" />}
          label="Cluster memory"
          value={`${totals.memory_usage}%`}
          sub={`${totals.memory_used.toFixed(0)}/${totals.memory_total.toFixed(0)} GB`}
        />
        <TotalCard
          icon={<Box className="h-6 w-6" />}
          label="Virtual machines"
          value={`${totals.vms.running}/${totals.vms.total}`}
          sub="running / total"
        />
        <TotalCard
          icon={<Boxes className="h-6 w-6" />}
          label="LXC containers"
          value={`${totals.lxc.running}/${totals.lxc.total}`}
          sub="running / total"
        />
      </div>

      {/* Per-node cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 md:gap-4">
        {nodes.map((n) => (
          <NodeCard key={n.name} node={n} />
        ))}
      </div>
    </div>
  )
}
