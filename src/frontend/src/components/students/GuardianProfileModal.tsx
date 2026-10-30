import { useState, useEffect, useCallback } from 'react';
import { X, Save, Sparkles, AlertTriangle, Check } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '../../lib/api';
import type { User, GuardianProfile, TemplateInfo } from '../../types';

interface GuardianProfileModalProps {
    isOpen: boolean;
    onClose: () => void;
    student: User | null;
}

type Tab = 'general' | 'persona' | 'safety';

export function GuardianProfileModal({ isOpen, onClose, student }: GuardianProfileModalProps) {
    const { t } = useTranslation(['students', 'common']);
    const [loading, setLoading] = useState(false);
    const [templates, setTemplates] = useState<TemplateInfo[]>([]);
    const [profile, setProfile] = useState<Partial<GuardianProfile>>({});
    const [selectedTemplate, setSelectedTemplate] = useState<string>('');
    const [activeTab, setActiveTab] = useState<Tab>('general');
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);

    const loadData = useCallback(async () => {
        if (!student) return;
        setLoading(true);
        setError(null);
        try {
            // Load templates
            const templatesRes = await api.get('/guardian-profiles/templates');
            setTemplates(templatesRes.data);

            // Load existing profile
            try {
                const profileRes = await api.get(`/guardian-profiles/students/${student.id}`);
                setProfile(profileRes.data);
                setSelectedTemplate(profileRes.data.template_name);
            } catch (e: any) { // eslint-disable-line @typescript-eslint/no-explicit-any
                if (e.response?.status === 404) {
                    // No profile yet, use default
                    setProfile({});
                    setSelectedTemplate('default');
                } else {
                    throw e;
                }
            }
        } catch {
            setError(t('errors.loadFailed', 'Failed to load profile data'));
        } finally {
            setLoading(false);
        }
    }, [student, t]);

    useEffect(() => {
        if (isOpen && student) {
            loadData();
        }
    }, [isOpen, student, loadData]);

    const handleSave = async () => {
        if (!student) return;
        setLoading(true);
        setError(null);
        setSuccess(null);

        try {
            const data = {
                ...profile,
                template_name: selectedTemplate
            };

            if (profile.id) {
                await api.put(`/guardian-profiles/students/${student.id}`, data);
            } else {
                await api.post(`/guardian-profiles/students/${student.id}`, data);
            }
            setSuccess(t('success.saved', 'Profile saved successfully'));
            setTimeout(onClose, 1500);
        } catch (e: any) { // eslint-disable-line @typescript-eslint/no-explicit-any
            setError(e.response?.data?.detail || t('errors.saveFailed', 'Failed to save profile'));
        } finally {
            setLoading(false);
        }
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
            <div className="glass-card w-full max-w-md p-6 max-h-[90vh] overflow-y-auto">
                {/* Header */}
                <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
                    <h2 className="text-xl font-bold flex items-center gap-2">
                        <Sparkles className="w-5 h-5 text-indigo-500" />
                        {t('guardianProfile', 'Guardian Profile')}: {student?.display_name}
                    </h2>
                    <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-full"><X className="w-6 h-6" /></button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-6">
                    {/* Tabs */}
                    <div className="flex gap-2 mb-6 border-b border-gray-200 dark:border-gray-700">
                        {['general', 'persona', 'safety'].map(tab => (
                            <button
                                key={tab}
                                onClick={() => setActiveTab(tab as Tab)}
                                className={`px-4 py-2 font-medium border-b-2 transition-colors ${activeTab === tab
                                        ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400'
                                        : 'border-transparent text-gray-500 hover:text-gray-700'
                                    }`}
                            >
                                {t(`tabs.${tab}`, tab.charAt(0).toUpperCase() + tab.slice(1))}
                            </button>
                        ))}
                    </div>

                    {loading && <div className="text-center py-8">Loading...</div>}

                    {!loading && activeTab === 'general' && (
                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium mb-1">Template</label>
                                <select
                                    value={selectedTemplate}
                                    onChange={(e) => setSelectedTemplate(e.target.value)}
                                    className="w-full p-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                                >
                                    {templates.map(t => (
                                        <option key={t.name} value={t.name}>{t.display_name}</option>
                                    ))}
                                </select>
                                <p className="text-xs text-gray-500 mt-1">
                                    {templates.find(t => t.name === selectedTemplate)?.description}
                                </p>
                            </div>

                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label htmlFor="age" className="block text-sm font-medium mb-1">Age</label>
                                    <input
                                        id="age"
                                        type="number"
                                        value={profile.age || ''}
                                        onChange={e => setProfile({ ...profile, age: parseInt(e.target.value) || undefined })}
                                        className="w-full p-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                                    />
                                </div>
                                <div>
                                    <label htmlFor="gender" className="block text-sm font-medium mb-1">Gender</label>
                                    <select
                                        id="gender"
                                        value={profile.gender || ''}
                                        onChange={e => setProfile({ ...profile, gender: e.target.value })}
                                        className="w-full p-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                                    >
                                        <option value="">Select...</option>
                                        <option value="male">Male</option>
                                        <option value="female">Female</option>
                                        <option value="non-binary">Non-binary</option>
                                    </select>
                                </div>
                            </div>
                        </div>
                    )}

                    {!loading && activeTab === 'persona' && (
                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium mb-1">Companion Name</label>
                                <input
                                    type="text"
                                    value={profile.companion_persona?.name || ''}
                                    onChange={e => setProfile({
                                        ...profile,
                                        companion_persona: { ...profile.companion_persona, name: e.target.value }
                                    })}
                                    className="w-full p-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                                    placeholder="e.g. Buddy, Robo"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium mb-1">Role</label>
                                <input
                                    type="text"
                                    value={profile.companion_persona?.role || ''}
                                    onChange={e => setProfile({
                                        ...profile,
                                        companion_persona: { ...profile.companion_persona, role: e.target.value }
                                    })}
                                    className="w-full p-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                                    placeholder="e.g. Teacher, Friend, Assistant"
                                />
                            </div>
                        </div>
                    )}

                    {!loading && activeTab === 'safety' && (
                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium mb-1">Content Filter Level</label>
                                <select
                                    value={profile.safety_constraints?.content_filter_level || 'standard'}
                                    onChange={e => setProfile({
                                        ...profile,
                                        safety_constraints: { ...profile.safety_constraints, content_filter_level: e.target.value }
                                    })}
                                    className="w-full p-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                                >
                                    <option value="strict">Strict</option>
                                    <option value="standard">Standard</option>
                                    <option value="relaxed">Relaxed</option>
                                </select>
                            </div>
                        </div>
                    )}

                    {error && (
                        <div className="mt-4 p-3 bg-red-50 text-red-600 rounded-lg flex items-center gap-2">
                            <AlertTriangle className="w-5 h-5" />
                            {error}
                        </div>
                    )}
                    {success && (
                        <div className="mt-4 p-3 bg-green-50 text-green-600 rounded-lg flex items-center gap-2">
                            <Check className="w-5 h-5" />
                            {success}
                        </div>
                    )}

                </div>

                {/* Footer */}
                <div className="p-6 border-t border-gray-200 dark:border-gray-700 flex justify-end gap-3">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg"
                    >
                        {t('cancel', 'Cancel')}
                    </button>
                    <button
                        onClick={handleSave}
                        disabled={loading}
                        className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-2"
                    >
                        <Save className="w-4 h-4" />
                        {t('save', 'Save Profile')}
                    </button>
                </div>
            </div>
        </div>
    );
}
