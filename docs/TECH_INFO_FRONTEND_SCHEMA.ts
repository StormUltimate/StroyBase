// StroyBase — схема данных для фронтенда (этаж, план, материалы, отклонения)
// Этот файл — вспомогательная документация для будущего React/PWA-клиента.
// Бэкенд-модели находятся в app/models.py (Floor, Plan, FloorMaterial, MaterialMovement, Document и др.).

export type UUID = string;

export interface BaseEntity {
  id: UUID;
  createdAt: string;
  updatedAt: string;
}

// Проект / Корпус / Этаж (упрощённое представление для фронтенда)

export interface Project extends BaseEntity {
  name: string;
  contractNumber?: string;
  address?: string;
}

export interface Building extends BaseEntity {
  projectId: UUID;
  name: string;
  floors: FloorSummary[];
}

export interface FloorSummary {
  id: UUID;
  name: string;
  floorType?: string;
}

export interface Floor extends BaseEntity {
  buildingId: UUID;
  projectId: UUID;
  name: string;
  floorType?: string;
  note?: string;
  areaM2?: number | null;
  totalAreaM2?: number | null;
  plan2d?: FloorPlan | null;
  materials: MaterialOnFloor[];
  certificates: CertificateFile[];
  asBuiltChanges: AsBuiltChange[];
}

// План этажа (2D), совместимый с SVG/Canvas и экспортом в GLTF

export type FloorPlanUnit = 'mm' | 'cm' | 'm';

export interface FloorPlan extends BaseEntity {
  floorId: UUID;
  version: number;
  name: string;
  width: number;
  height: number;
  unit: FloorPlanUnit;
  origin: { x: number; y: number };
  sourceFiles: {
    svgPath?: string;
    jsonPath?: string;
  };
  layers: PlanLayer[];
  walls: PlanWall[];
  doors: PlanDoor[];
  windows: PlanWindow[];
  rooms: PlanRoom[];
  hotspots: PlanHotspot[];
  extrusionDefaults: {
    wallHeightMm?: number;
    slabThicknessMm?: number;
  };
}

export interface PlanLayer {
  id: UUID;
  name: string;
  visible: boolean;
  opacity: number;
  zIndex: number;
  type?: 'structural' | 'partition' | 'finish' | 'furniture' | 'annotation';
}

export interface PlanPoint {
  id: UUID;
  x: number;
  y: number;
}

export interface PlanWall {
  id: UUID;
  layerId: UUID;
  start: PlanPoint;
  end: PlanPoint;
  thicknessMm?: number;
  materialCode?: string;
  roomIds?: UUID[];
}

export interface PlanDoor {
  id: UUID;
  layerId: UUID;
  position: PlanPoint;
  widthMm: number;
  swingDirection?: 'cw' | 'ccw';
  wallId?: UUID;
}

export interface PlanWindow {
  id: UUID;
  layerId: UUID;
  position: PlanPoint;
  widthMm: number;
  sillHeightMm?: number;
  wallId?: UUID;
}

export interface PlanRoom {
  id: UUID;
  name: string;
  code?: string;
  polygon: PlanPoint[];
  level?: number;
  defaultMaterialCodes?: string[];
}

export type PlanHotspotType = 'material' | 'photo' | 'note' | 'issue';

export interface PlanHotspot {
  id: UUID;
  type: PlanHotspotType;
  position: PlanPoint;
  label?: string;
  materialId?: UUID;
  attachments?: string[];
  meta?: Record<string, any>;
}

// Материалы этажа: справочник + план/факт по конкретному этажу

export type QuantityUnit = 'm2' | 'm3' | 'm' | 'kg' | 't' | 'pcs';

export interface MaterialDirectoryItem {
  id: UUID;
  code: string;
  name: string;
  unit: QuantityUnit;
  defaultPricePerUnit?: number;
  meta?: {
    manufacturer?: string;
    specificationUrl?: string;
    category?: string;
  };
}

export type DeviationSeverity = 'ok' | 'minor' | 'major' | 'critical';

export interface MaterialDeviation {
  hasDeviation: boolean;
  qtyDelta?: number;
  qtyDeltaPercent?: number;
  costDelta?: number;
  severity?: DeviationSeverity;
  comment?: string;
}

export interface MaterialOnFloor extends BaseEntity {
  floorId: UUID;
  materialId: UUID;
  roomId?: UUID;
  hotspotId?: UUID;
  planQty: number | null;
  factQty: number | null;
  unit: QuantityUnit;
  pricePerUnit: number | null;
  currency: string;
  totals: {
    planCost: number | null;
    factCost: number | null;
  };
  deviation: MaterialDeviation;
  certificateIds: UUID[];
}

export interface CertificateFile extends BaseEntity {
  floorId: UUID;
  materialId?: UUID;
  fileName: string;
  fileSize: number;
  mimeType: string;
  url: string;
  source?: 'upload' | 'link';
  externalUrl?: string;
  description?: string;
  issueDate?: string;
  expiryDate?: string;
}

// As-built изменения для будущей AR/WebXR-интеграции

export type AsBuiltTargetType =
  | 'wall'
  | 'door'
  | 'window'
  | 'room'
  | 'hotspot'
  | 'material';

export type AsBuiltChangeType = 'create' | 'update' | 'delete';

export interface AsBuiltChange extends BaseEntity {
  floorId: UUID;
  targetType: AsBuiltTargetType;
  targetId: UUID | null;
  changeType: AsBuiltChangeType;
  payloadBefore?: Record<string, any>;
  payloadAfter?: Record<string, any>;
  source: 'manual' | 'ar-scan' | 'import' | 'api';
  authorId?: UUID;
  comment?: string;
  arRef?: {
    modelElementId?: string;
    worldPosition?: { x: number; y: number; z: number };
  };
}

