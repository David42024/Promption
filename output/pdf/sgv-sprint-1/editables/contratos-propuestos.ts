/** Propuesta para alinear Frontend y Backend; no es un contrato aprobado ni código del SGV. */
export type ID = string;
export type ISODateTime = string;
export type VolunteerStatus = 'applicant' | 'selection' | 'active' | 'inactive' | 'retired';
export type UserStatus = 'pending_activation' | 'active' | 'deactivated';
export type PeriodCode = 'Q1' | 'Q2' | 'Q3' | 'CLOSURE';
export interface Option { value: ID; label: string }

export interface Context {
  management: Option;
  period: (Option & { code: PeriodCode }) | null;
  availableManagements: Option[];
}

/** Capacidades estructurales. La elevación sensible se evalúa aparte en servidor. */
export interface SharedProps {
  auth: {
    user: { id: ID; name: string; email: string } | null;
    can: Record<string, boolean>;
    sensitiveSession: {
      isElevated: boolean;
      expiresAt: ISODateTime | null;
      serverNow: ISODateTime;
    };
  };
  context: Context | null;
  flash: { success?: string; error?: string };
}

export interface VolunteerSummary {
  id: ID;
  fullName: string;
  dniDisplay: string;
  area: Option;
  status: VolunteerStatus;
  statusLabel: string;
  account: { id: ID; status: UserStatus; statusLabel: string } | null;
  can: { view: boolean; changeStatus: boolean };
}

/** Si no hay permiso, el servidor omite tanto la pestaña como sus datos. */
export interface VolunteerDetail extends VolunteerSummary {
  managementId: ID;
  identity: {
    dni: string;
    email: string | null;
    photoUrl: string | null;
    universityCode: string | null;
    degree: string | null;
    cycle: string | null;
  };
  availableTabs: Array<'identity' | 'metrics' | 'projects' | 'sanctions' | 'restricted'>;
  metrics?: {
    availability: 'available' | 'no_data' | 'not_implemented';
    presencialHours: number | null;
    virtualHours: number | null;
    virtualAreaMeetingAttendancePercent: number | null;
    incuPoints: number | null;
  };
  projects?: Array<{ id: ID; name: string; role: string; statusLabel: string }>;
  sanctions?: Array<{ id: ID; date: string; type: string; description: string }>;
  restricted?: {
    bloodType: string | null;
    emergencyContact: { name: string; phone: string } | null;
    climateNotes: string | null;
  };
  history: Array<{ management: Option; statusLabel: string; area: Option }>;
  allowedTransitions: Array<{
    to: VolunteerStatus;
    label: string;
    requiresSensitiveSession: boolean;
    effects: string[];
  }>;
}

export interface Paginated<T> {
  data: T[];
  meta: { page: number; perPage: number; total: number; lastPage: number };
  links: Array<{ label: string; url: string | null; active: boolean }>;
}
export interface VolunteerIndexProps extends SharedProps {
  volunteers: Paginated<VolunteerSummary>;
  filters: { query: string; managementId: ID; areaId: ID | null; status: VolunteerStatus | null };
  filterOptions: { areas: Option[]; statuses: Option[] };
}
export interface CreateUserProps extends SharedProps {
  allowedRoles: Option[];
  allowedAreas: Option[];
  allowedSubareas: Option[];
}
export interface CreateUserPayload {
  names: string;
  surnames: string;
  email: string;
  roleId: ID;
  areaId: ID | null;
  subareaId: ID | null;
  volunteerId: ID | null;
  managementId: ID;
}
export interface Period {
  id: ID;
  managementId: ID;
  code: PeriodCode;
  label: string;
  startDate: string;
  endDate: string;
}

/** La intención pendiente se ejecuta una vez; el mecanismo concreto se acuerda con Backend. */
export interface SensitiveIntent {
  id: ID;
  status: 'awaiting_email' | 'authorized' | 'completed' | 'expired' | 'failed';
  confirmationExpiresAt: ISODateTime | null;
  returnUrl: string;
}
export interface TransitionResult {
  volunteer: VolunteerSummary;
  effects: { accountDeactivated: boolean; assignmentsDetached: number; historyPreserved: boolean };
}
