import { mockInterviewService } from './mockInterviewService.js';
import { createRealInterviewService } from './realInterviewService.js';

export const serviceMode = import.meta.env.VITE_INTERVIEW_SERVICE || 'mock';
if (!['mock', 'real'].includes(serviceMode)) throw new Error('VITE_INTERVIEW_SERVICE must be mock or real.');
export const interviewService = serviceMode === 'real'
  ? createRealInterviewService({ baseUrl: import.meta.env.VITE_API_BASE_URL === 'same-origin'
    ? window.location.origin : import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000' })
  : mockInterviewService;
