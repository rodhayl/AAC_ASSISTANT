import { useState, useEffect, useCallback } from 'react';
import { X, Save, Sparkles, AlertTriangle, Check } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api, { extractError } from '../../lib/api';
import type { User, GuardianProfile, TemplateInfo } from '../../types';
import { Button } from '../ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';

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
        // Clear any success state left by a previous student: reopening the
        // modal for another student must not keep showing the old toast text.
        setSuccess(null);
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
            setError(t('students:errors.profileLoadFailed'));
        } finally {
            setLoading(false);
        }
    }, [student, t]);

    useEffect(() => {
        if (!isOpen || !success) return;
        const timeoutId = setTimeout(onClose, 1500);
        return () => clearTimeout(timeoutId);
    }, [isOpen, onClose, success]);

    useEffect(() => {
        if (!isOpen && success) setSuccess(null);
    }, [isOpen, success]);

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
            setSuccess(t('students:success.saved'));
        } catch (e: any) { // eslint-disable-line @typescript-eslint/no-explicit-any
            setError(extractError(e, t('students:errors.saveFailed')));
        } finally {
            setLoading(false);
        }
    };

    if (!isOpen) return null;

    return (
        <Dialog open={isOpen} onOpenChange={(open) => { if (!open) onClose(); }}>
            <DialogContent
                showCloseButton={false}
                className="max-w-md p-0 max-h-[90vh] overflow-hidden"
            >
                {/* Header */}
                <DialogHeader className="flex-row items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
                    <DialogTitle className="text-xl font-bold flex items-center gap-2">
                        <Sparkles className="w-5 h-5 text-indigo-500" />
                        {t('students:guardianProfile')}: {student?.display_name}
                    </DialogTitle>
                    <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-full" aria-label={t('common:close')}><X className="w-6 h-6" /></button>
                </DialogHeader>

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

                    {loading && <div className="text-center py-8">{t('students:loading')}</div>}

                    {!loading && activeTab === 'general' && (
                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium mb-1">{t('students:template')}</label>
                                <Select
                                    value={selectedTemplate}
                                    onValueChange={(value) => setSelectedTemplate(value ?? selectedTemplate)}
                                    items={templates.map((tpl) => ({ value: tpl.name, label: tpl.display_name }))}
                                >
                                    <SelectTrigger aria-label={t('students:template')} className="w-full">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {templates.map(tpl => (
                                            <SelectItem key={tpl.name} value={tpl.name}>{tpl.display_name}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                                <p className="text-xs text-gray-500 mt-1 dark:text-gray-400">
                                    {templates.find(t => t.name === selectedTemplate)?.description}
                                </p>
                            </div>

                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label htmlFor="age" className="block text-sm font-medium mb-1">{t('students:age')}</label>
                                    <input
                                        id="age"
                                        type="number"
                                        value={profile.age || ''}
                                        onChange={e => setProfile({ ...profile, age: parseInt(e.target.value) || undefined })}
                                        className="w-full p-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                                    />
                                </div>
                                <div>
                                    <label htmlFor="gender" className="block text-sm font-medium mb-1">{t('students:gender')}</label>
                                    <select
                                        id="gender"
                                        value={profile.gender || ''}
                                        onChange={e => setProfile({ ...profile, gender: e.target.value })}
                                        className="w-full p-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                                    >
                                        <option value="">{t('students:select')}</option>
                                        <option value="male">{t('students:male')}</option>
                                        <option value="female">{t('students:female')}</option>
                                        <option value="non-binary">{t('students:nonBinary')}</option>
                                    </select>
                                </div>
                            </div>
                        </div>
                    )}

                    {!loading && activeTab === 'persona' && (
                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium mb-1">{t('students:companionName')}</label>
                                <input
                                    type="text"
                                    value={profile.companion_persona?.name || ''}
                                    onChange={e => setProfile({
                                        ...profile,
                                        companion_persona: { ...profile.companion_persona, name: e.target.value }
                                    })}
                                    className="w-full p-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                                    placeholder={t('placeholders.companionName')}
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium mb-1">{t('students:role')}</label>
                                <input
                                    type="text"
                                    value={profile.companion_persona?.role || ''}
                                    onChange={e => setProfile({
                                        ...profile,
                                        companion_persona: { ...profile.companion_persona, role: e.target.value }
                                    })}
                                    className="w-full p-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                                    placeholder={t('placeholders.role')}
                                />
                            </div>
                        </div>
                    )}

                    {!loading && activeTab === 'safety' && (
                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium mb-1">{t('students:contentFilterLevel')}</label>
                                <select
                                    value={profile.safety_constraints?.content_filter_level || 'standard'}
                                    onChange={e => setProfile({
                                        ...profile,
                                        safety_constraints: { ...profile.safety_constraints, content_filter_level: e.target.value }
                                    })}
                                    className="w-full p-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                                >
                                    <option value="strict">{t('students:strict')}</option>
                                    <option value="standard">{t('students:standard')}</option>
                                    <option value="relaxed">{t('students:relaxed')}</option>
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
                        {t('students:cancel')}
                    </button>
                    <Button onClick={handleSave} disabled={loading} className="flex items-center gap-2" >
                        <Save className="w-4 h-4" />
                        {t('save')}
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    );
}
