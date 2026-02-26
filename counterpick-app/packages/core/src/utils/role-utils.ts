/**
 * Role-bezogene Utility-Funktionen
 */

import type { Role, RoleId } from '../types/draft';

/**
 * Konvertiert Role ID zu Role Name
 */
export function roleIdToName(roleId: RoleId): Role {
    const mapping: Record<RoleId, Role> = {
        0: 'top',
        1: 'jungle',
        2: 'middle',
        3: 'bottom',
        4: 'support'
    };
    return mapping[roleId];
}

/**
 * Konvertiert Role Name zu Role ID
 */
export function roleNameToId(role: Role): RoleId {
    const mapping: Record<Role, RoleId> = {
        'top': 0,
        'jungle': 1,
        'middle': 2,
        'bottom': 3,
        'support': 4
    };
    return mapping[role];
}

/**
 * Normalisiert Role-Eingabe zu Standard-Format
 */
export function normalizeRole(roleInput: string | number | null | undefined): Role | '' {
    if (roleInput === null || roleInput === undefined) return '';
    
    const r = String(roleInput).toLowerCase().trim();
    
    // Numerische IDs
    if (r === '0') return 'top';
    if (r === '1') return 'jungle';
    if (r === '2') return 'middle';
    if (r === '3') return 'bottom';
    if (r === '4') return 'support';
    
    // Alternative Namen
    if (r === 'mid') return 'middle';
    if (r === 'adc' || r === 'bot') return 'bottom';
    if (r === 'utility' || r === 'supp') return 'support';
    if (r === 'jg' || r === 'jng') return 'jungle';
    
    // Standard-Namen
    if (['top', 'jungle', 'middle', 'bottom', 'support'].includes(r)) {
        return r as Role;
    }
    
    return '';
}

/**
 * Gibt den Anzeigenamen für eine Rolle zurück
 */
export function getRoleDisplayName(role: Role | string): string {
    const displayNames: Record<string, string> = {
        'top': 'Top',
        'jungle': 'Jungle',
        'middle': 'Mid',
        'bottom': 'ADC',
        'support': 'Support'
    };
    return displayNames[role] || role;
}

/**
 * Liste aller Rollen
 */
export const ALL_ROLES: Role[] = ['top', 'jungle', 'middle', 'bottom', 'support'];

