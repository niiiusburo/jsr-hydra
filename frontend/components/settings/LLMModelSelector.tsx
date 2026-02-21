'use client'

import { useState, useEffect, useCallback } from 'react'
import { Brain, Check, Loader2, Save, AlertCircle, ChevronDown, Eye, EyeOff, KeyRound } from 'lucide-react'
import { getLLMConfig, updateLLMConfig, LLMConfig } from '@/lib/api'

const PROVIDER_DISPLAY: Record<string, { name: string; description: string }> = {
  openai: { name: 'OpenAI', description: 'GPT-4o, GPT-4 Turbo' },
  zai: { name: 'Z.AI', description: 'Zeus, Athena models' },
}

export function LLMModelSelector() {
  const [config, setConfig] = useState<LLMConfig | null>(null)
  const [selectedProvider, setSelectedProvider] = useState<string>('')
  const [selectedModel, setSelectedModel] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [apiKey, setApiKey] = useState<string>('')
  const [showApiKey, setShowApiKey] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  const fetchConfig = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await getLLMConfig()
      setConfig(data)
      setSelectedProvider(data.provider)
      setSelectedModel(data.model)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load LLM configuration')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchConfig()
  }, [fetchConfig])

  // Clear success message after 3 seconds
  useEffect(() => {
    if (success) {
      const timer = setTimeout(() => setSuccess(false), 3000)
      return () => clearTimeout(timer)
    }
  }, [success])

  // When provider changes, pick the first available model for that provider
  const handleProviderSelect = (provider: string) => {
    setSelectedProvider(provider)
    if (config?.models[provider]?.length) {
      setSelectedModel(config.models[provider][0])
    }
  }

  const isDirty =
    config !== null &&
    (selectedProvider !== config.provider || selectedModel !== config.model || apiKey.trim().length > 0)

  const handleApply = async () => {
    try {
      setSaving(true)
      setError(null)
      const trimmedKey = apiKey.trim() || undefined
      const data = await updateLLMConfig(selectedProvider, selectedModel, trimmedKey)
      setConfig(data)
      setSelectedProvider(data.provider)
      setSelectedModel(data.model)
      setApiKey('')
      setShowApiKey(false)
      setSuccess(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update LLM configuration')
    } finally {
      setSaving(false)
    }
  }

  const availableModels = config?.models[selectedProvider] || []

  return (
    <div className="rounded-xl border border-gray-700/50 bg-[#0d1f3c]/80 p-6 backdrop-blur-sm">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-[#00d97e]/10 border border-[#00d97e]/20">
          <Brain className="w-5 h-5 text-[#00d97e]" />
        </div>
        <div>
          <h2 className="text-xl font-bold text-gray-100">LLM Model</h2>
          <p className="text-sm text-gray-500">Configure the AI provider for trade analysis</p>
        </div>
      </div>

      {/* Loading State */}
      {loading && (
        <div className="flex flex-col items-center justify-center py-12 gap-3">
          <Loader2 className="w-8 h-8 text-[#00d97e] animate-spin" />
          <p className="text-sm text-gray-500">Loading LLM config...</p>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="flex items-center gap-2 px-4 py-3 mb-4 rounded-lg bg-[#e63757]/10 border border-[#e63757]/30">
          <AlertCircle className="w-4 h-4 text-[#e63757] shrink-0" />
          <p className="text-sm text-[#e63757]">{error}</p>
        </div>
      )}

      {/* Success Toast */}
      {success && (
        <div className="flex items-center gap-2 px-4 py-3 mb-4 rounded-lg bg-[#00d97e]/10 border border-[#00d97e]/30">
          <Check className="w-4 h-4 text-[#00d97e] shrink-0" />
          <p className="text-sm text-[#00d97e]">LLM configuration updated successfully</p>
        </div>
      )}

      {/* Last Error from Backend */}
      {config?.last_error && (
        <div className="flex items-start gap-2 px-4 py-3 mb-4 rounded-lg bg-yellow-500/5 border border-yellow-500/20">
          <AlertCircle className="w-4 h-4 text-yellow-500 shrink-0 mt-0.5" />
          <div>
            <p className="text-xs font-medium text-yellow-500 mb-1">Last LLM Error</p>
            <p className="text-xs text-yellow-500/80 font-mono">{config.last_error}</p>
          </div>
        </div>
      )}

      {!loading && config && (
        <>
          {/* Provider Cards */}
          <div className="grid grid-cols-2 gap-3 mb-6">
            {config.providers.map((provider) => {
              const isActive = selectedProvider === provider.provider
              const display = PROVIDER_DISPLAY[provider.provider] || {
                name: provider.provider,
                description: provider.default_model,
              }

              return (
                <button
                  key={provider.provider}
                  onClick={() => handleProviderSelect(provider.provider)}
                  className={`
                    relative flex flex-col items-start gap-2 px-5 py-4 rounded-xl border
                    transition-all duration-200 cursor-pointer select-none text-left
                    ${
                      isActive
                        ? 'border-[#00d97e] bg-[#00d97e]/10 shadow-[0_0_15px_rgba(0,217,126,0.15)]'
                        : 'border-gray-700 bg-gray-900/50 hover:border-gray-600 hover:bg-gray-900/70'
                    }
                  `}
                >
                  {/* Check badge */}
                  {isActive && (
                    <div className="absolute top-3 right-3 flex items-center justify-center w-5 h-5 rounded-full bg-[#00d97e]">
                      <Check className="w-3 h-3 text-[#0a1628]" />
                    </div>
                  )}

                  {/* Provider name */}
                  <span className={`text-sm font-bold tracking-wide ${isActive ? 'text-[#00d97e]' : 'text-gray-300'}`}>
                    {display.name}
                  </span>

                  {/* API key status */}
                  <div className="flex items-center gap-1.5">
                    <div
                      className={`w-2 h-2 rounded-full ${
                        provider.configured ? 'bg-[#00d97e] shadow-[0_0_6px_rgba(0,217,126,0.5)]' : 'bg-[#e63757]'
                      }`}
                    />
                    <span className={`text-xs ${provider.configured ? 'text-gray-400' : 'text-gray-600'}`}>
                      {provider.configured ? 'API Key Set' : 'Not Configured'}
                    </span>
                  </div>

                  {/* Default model */}
                  <span className={`text-xs font-mono ${isActive ? 'text-[#00d97e]/50' : 'text-gray-600'}`}>
                    {provider.default_model}
                  </span>
                </button>
              )
            })}
          </div>

          {/* Model Dropdown */}
          <div className="mb-6">
            <label className="block text-xs font-medium text-gray-500 mb-2 uppercase tracking-wider">
              Model
            </label>
            <div className="relative">
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="
                  w-full appearance-none px-4 py-3 rounded-xl
                  bg-gray-900/70 border border-gray-700 text-gray-200
                  text-sm font-mono
                  focus:outline-none focus:border-[#00d97e]/50 focus:ring-1 focus:ring-[#00d97e]/20
                  transition-all duration-200 cursor-pointer
                "
              >
                {availableModels.length === 0 && (
                  <option value="">No models available</option>
                )}
                {availableModels.map((model) => (
                  <option key={model} value={model}>
                    {model}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500 pointer-events-none" />
            </div>
          </div>

          {/* API Key Input */}
          <div className="mb-6">
            <label className="block text-xs font-medium text-gray-500 mb-2 uppercase tracking-wider">
              <div className="flex items-center gap-1.5">
                <KeyRound className="w-3 h-3" />
                API Key
              </div>
            </label>
            <div className="relative">
              <input
                type={showApiKey ? 'text' : 'password'}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={
                  config?.providers.find((p) => p.provider === selectedProvider)?.configured
                    ? 'Key is set — enter new key to replace'
                    : 'Enter API key for this provider'
                }
                className="
                  w-full px-4 py-3 pr-12 rounded-xl
                  bg-gray-900/70 border border-gray-700 text-gray-200
                  text-sm font-mono placeholder-gray-600
                  focus:outline-none focus:border-[#00d97e]/50 focus:ring-1 focus:ring-[#00d97e]/20
                  transition-all duration-200
                "
              />
              <button
                type="button"
                onClick={() => setShowApiKey(!showApiKey)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 transition-colors"
              >
                {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Apply Button */}
          <button
            onClick={handleApply}
            disabled={!isDirty || saving}
            className={`
              flex items-center justify-center gap-2 w-full py-3 rounded-xl font-semibold text-sm
              transition-all duration-200
              ${
                isDirty
                  ? 'bg-[#00d97e] text-[#0a1628] hover:bg-[#00d97e]/90 shadow-[0_0_20px_rgba(0,217,126,0.2)]'
                  : 'bg-gray-800 text-gray-600 cursor-not-allowed'
              }
            `}
          >
            {saving ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            {saving ? 'Applying...' : 'Apply'}
          </button>
        </>
      )}
    </div>
  )
}
