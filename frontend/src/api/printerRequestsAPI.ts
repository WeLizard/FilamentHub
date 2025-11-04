/**Printer Requests API for users. */

import api from './client';
import type { PrinterRequest } from '../types/api';

export const printerRequestsAPI = {
  create: async (data: {
    name: string;
    manufacturer: string;
    model: string;
    slug: string;
    description?: string;
    build_volume_x?: number;
    build_volume_y?: number;
    build_volume_z?: number;
    nozzle_diameter?: number;
    max_extruder_temp?: number;
    max_bed_temp?: number;
    image_url?: string;
    message?: string;
  }): Promise<PrinterRequest> => {
    const response = await api.post<PrinterRequest>('/printer-requests/', data);
    return response.data;
  },

  listMy: async (params?: { 
    page?: number; 
    size?: number; 
    status?: 'pending' | 'approved' | 'rejected';
  }): Promise<{ items: PrinterRequest[]; total: number }> => {
    const response = await api.get<{ items: PrinterRequest[]; total: number }>('/printer-requests/', { params });
    return response.data;
  },

  get: async (id: number): Promise<PrinterRequest> => {
    const response = await api.get<PrinterRequest>(`/printer-requests/${id}`);
    return response.data;
  },
};

