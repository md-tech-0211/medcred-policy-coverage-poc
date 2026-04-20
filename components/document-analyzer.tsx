"use client"

import type React from "react"

import { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { FileText, Upload, Brain, Shield, CheckCircle, AlertCircle, Loader2, X } from "lucide-react"

interface AnalysisResult {
  files_processed: number
  file_metadata: Array<{
    filename: string
    original_name: string
    extension: string
    status: string
  }>
  email: string
  policy_name: string
  policy_context_retrieved: boolean
  combined_ocr_text: string
  individual_extracted_texts: string[]
  individual_cleaned_texts: string[]
  agent1_response: string
  agent2_response: string
  judge?: { status: string; confidence?: number; rationale?: string } | string
  database_ids: {
    user_id: number
    session_id: number
    request_id: number
    agent1_response_id: number
    agent2_response_id: number
    judge_id: number
  }
  file_metadata_json: {
    files: Array<{
      file_index: number
      filename: string
      original_name: string
      extension: string
      status: string
      text_length: number
      error: string | null
    }>
    processing_summary: {
      total_files: number
      successful_files: number
      failed_files: number
    }
  }
}

export function DocumentAnalyzer() {
  const [files, setFiles] = useState<File[]>([])
  const [email, setEmail] = useState("")
  const [query, setQuery] = useState("")
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const newFiles = Array.from(e.target.files)
      setFiles((prev) => [...prev, ...newFiles])
    }
  }

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (files.length === 0 || !query) return

    setIsAnalyzing(true)
    setError(null)
    setResult(null)

    try {
      const formData = new FormData()

      // Add all files to the same form data
      files.forEach((file) => {
        formData.append("file", file)
      })

      // Add email only if provided
      if (email.trim()) {
        formData.append("email", email)
      }

      formData.append("query", query)

      const response = await fetch("https://md3qpv3zcsn5evgofzzfo4ahre0qjrbm.lambda-url.us-west-2.on.aws/", {
        method: "POST",
        body: formData,
      })

      if (!response.ok) {
        throw new Error(`Analysis failed`)
      }

      const data = await response.json()
      console.log("[v0] Full API Response:", data)
      console.log("[v0] API Response Type:", typeof data)
      console.log("[v0] API Response Keys:", Object.keys(data))
      setResult(data)
    } catch (err) {
      setError("Failed to analyze documents. Please try again.")
      console.log("[v0] API Error:", err)
    } finally {
      setIsAnalyzing(false)
    }
  }

  const parseJudgeResponse = (judgeText: string) => {
    try {
      const jsonMatch = judgeText.match(/```json\n([\s\S]*?)\n```/)
      if (jsonMatch) {
        return JSON.parse(jsonMatch[1])
      }
    } catch (e) {
      // Fallback to raw text if JSON parsing fails
    }
    return null
  }

  const getFinalAssessment = (judgeField: AnalysisResult["judge"]) => {
    if (!judgeField) return null

    // New format: object with status/confidence/rationale
    if (typeof judgeField === "object") {
      const status = judgeField.status?.trim()
      const rationale = judgeField.rationale?.toString() || ""
      const confidence = typeof judgeField.confidence === "number" ? judgeField.confidence : undefined

      if (status) {
        return { status, rationale, confidence }
      }
      return null
    }

    // Old format: string possibly containing fenced JSON with winner/reason
    if (typeof judgeField === "string") {
      try {
        const fenced = judgeField.match(/```json\s*([\s\S]*?)\s*```/)
        const raw = fenced ? fenced[1] : judgeField
        const parsed = JSON.parse(raw)
        // Map old fields to new display
        const rationale = parsed.reason || parsed.rationale || judgeField
        // We can't infer covered/not covered reliably from "winner"; default to Unsure
        return { status: "Unsure", rationale, confidence: undefined }
      } catch {
        // Fallback: show text as rationale, unsure status
        return { status: "Unsure", rationale: judgeField, confidence: undefined }
      }
    }

    return null
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-6xl">
      {/* Header */}
      <div className="text-center mb-12">
        <div className="flex items-center justify-center gap-3 mb-4">
          <div className="p-3 rounded-lg bg-primary/10">
            <FileText className="h-8 w-8 text-primary" />
          </div>
          <h1 className="text-4xl font-bold text-balance">Medical Document Analyzer</h1>
        </div>
        <p className="text-xl text-muted-foreground text-balance max-w-2xl mx-auto">
          Upload multiple prescriptions or medical documents to get AI-powered insurance coverage analysis
        </p>
      </div>

      <div className="grid lg:grid-cols-2 gap-8">
        {/* Upload Form */}
        <Card className="border-border/50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Upload className="h-5 w-5" />
              Document Upload
            </CardTitle>
            <CardDescription>Upload your medical documents and provide your query details</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-6">
              <div className="space-y-2">
                <Label htmlFor="file">Medical Documents</Label>
                <Input
                  id="file"
                  type="file"
                  accept="image/*,.pdf"
                  multiple
                  onChange={handleFileChange}
                  className="cursor-pointer"
                />
                {files.length > 0 && (
                  <div className="space-y-2 mt-3">
                    <Label className="text-sm text-muted-foreground">Selected Files ({files.length})</Label>
                    <div className="space-y-2 max-h-32 overflow-y-auto">
                      {files.map((file, index) => (
                        <div key={index} className="flex items-center justify-between gap-2 p-2 bg-muted/30 rounded-md">
                          <div className="flex items-center gap-2 text-sm">
                            <FileText className="h-4 w-4" />
                            <span className="truncate">{file.name}</span>
                          </div>
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={() => removeFile(index)}
                            className="h-6 w-6 p-0 hover:bg-destructive/10"
                          >
                            <X className="h-3 w-3" />
                          </Button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="email">Email Address (Optional)</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="your.email@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="query">Insurance Query</Label>
                <Textarea
                  id="query"
                  placeholder="e.g., Will this medication be covered in my insurance policy?"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  rows={3}
                />
              </div>

              <Button type="submit" className="w-full" disabled={files.length === 0 || !query || isAnalyzing}>
                {isAnalyzing ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Analyzing {files.length} Document{files.length > 1 ? "s" : ""}...
                  </>
                ) : (
                  <>
                    <Brain className="mr-2 h-4 w-4" />
                    Analyze {files.length > 0 ? `${files.length} Document${files.length > 1 ? "s" : ""}` : "Documents"}
                  </>
                )}
              </Button>
            </form>
          </CardContent>
        </Card>

        {/* Results */}
        <div className="space-y-6">
          {error && (
            <Card className="border-destructive/50 bg-destructive/5">
              <CardContent className="pt-6">
                <div className="flex items-center gap-2 text-destructive">
                  <AlertCircle className="h-5 w-5" />
                  <span className="font-medium">{error}</span>
                </div>
              </CardContent>
            </Card>
          )}

          {result && (
            <div className="space-y-8">
              {/* Processing Summary */}
              {result.file_metadata_json?.processing_summary && (
                <Card className="border-border/50">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <CheckCircle className="h-5 w-5 text-accent" />
                      Processing Summary
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-3 gap-4 text-center">
                      <div>
                        <p className="text-2xl font-bold text-primary">
                          {result.file_metadata_json.processing_summary.total_files}
                        </p>
                        <p className="text-sm text-muted-foreground">Total Files</p>
                      </div>
                      <div>
                        <p className="text-2xl font-bold text-accent">
                          {result.file_metadata_json.processing_summary.successful_files}
                        </p>
                        <p className="text-sm text-muted-foreground">Successful</p>
                      </div>
                      <div>
                        <p className="text-2xl font-bold text-destructive">
                          {result.file_metadata_json.processing_summary.failed_files}
                        </p>
                        <p className="text-sm text-muted-foreground">Failed</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Analysis Summary */}
              <Card className="border-border/50">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Shield className="h-5 w-5" />
                    Analysis Summary
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    {result.policy_name && result.policy_name.trim() && result.policy_name !== "null" && (
                      <div>
                        <Label className="text-sm text-muted-foreground">Policy Name</Label>
                        <p className="font-medium">{result.policy_name}</p>
                      </div>
                    )}
                    {result.email && (
                      <div>
                        <Label className="text-sm text-muted-foreground">Email</Label>
                        <p className="font-medium">{result.email}</p>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>

              {/* File Details */}
              {result.file_metadata_json?.files && result.file_metadata_json.files.length > 0 && (
                <Card className="border-border/50">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <FileText className="h-5 w-5" />
                      File Processing Details
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3">
                      {result.file_metadata_json.files.map((file, index) => (
                        <div key={index} className="flex items-center justify-between p-3 bg-muted/30 rounded-lg">
                          <div className="flex items-center gap-3">
                            <FileText className="h-4 w-4" />
                            <div>
                              <p className="font-medium text-sm">{file.original_name}</p>
                              <p className="text-xs text-muted-foreground">
                                {file.text_length} characters extracted • {file.extension.toUpperCase()}
                              </p>
                            </div>
                          </div>
                          <Badge variant={file.status === "success" ? "default" : "destructive"}>{file.status}</Badge>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* AI Analysis */}
              {(result.agent1_response || result.agent2_response || result.judge) && (
                <Card className="border-border/50">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Brain className="h-5 w-5" />
                      AI Analysis Results
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    <div className="space-y-4">
                      {result.agent1_response && (
                        <div>
                          <div className="flex items-center gap-2 mb-2">
                            <Badge variant="secondary">Agent 1</Badge>
                          </div>
                          <p className="text-sm leading-relaxed">{result.agent1_response}</p>
                        </div>
                      )}

                      {result.agent1_response && result.agent2_response && <Separator />}

                      {result.agent2_response && (
                        <div>
                          <div className="flex items-center gap-2 mb-2">
                            <Badge variant="secondary">Agent 2</Badge>
                          </div>
                          <p className="text-sm leading-relaxed">{result.agent2_response}</p>
                        </div>
                      )}

                      {/* Final Assessment */}
                      {(() => {
                        const fa = getFinalAssessment(result.judge)
                        if (!fa) return null

                        // choose semantic color token for status text
                        const statusClass =
                          fa.status?.toLowerCase() === "covered"
                            ? "text-accent"
                            : fa.status?.toLowerCase() === "not covered"
                              ? "text-destructive"
                              : "text-muted-foreground"

                        return (
                          <>
                            <Separator />
                            <div>
                              <div className="flex items-center gap-2 mb-2">
                                <Badge variant="outline">Final Assessment</Badge>
                              </div>
                              <p className={`text-sm leading-relaxed font-medium ${statusClass}`}>
                                Status: {fa.status || "Unsure"}
                                {typeof fa.confidence === "number"
                                  ? ` • Confidence: ${Math.round(fa.confidence * 100)}%`
                                  : ""}
                              </p>
                              {fa.rationale && (
                                <p className="text-sm leading-relaxed text-muted-foreground mt-1">{fa.rationale}</p>
                              )}
                            </div>
                          </>
                        )
                      })()}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Individual Document Texts */}
              {result.individual_cleaned_texts &&
                result.individual_cleaned_texts.length > 0 &&
                result.individual_cleaned_texts.map((text, index) => (
                  <Card key={index} className="border-border/50">
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <FileText className="h-5 w-5" />
                        Document {index + 1}: {result.file_metadata?.[index]?.original_name || `File ${index + 1}`}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="bg-muted/30 rounded-lg p-4">
                        <pre className="text-sm whitespace-pre-wrap font-mono leading-relaxed">{text}</pre>
                      </div>
                    </CardContent>
                  </Card>
                ))}

              {/* Combined OCR Text */}
              {result.combined_ocr_text && (
                <Card className="border-border/50">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <FileText className="h-5 w-5" />
                      Combined Document Text
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="bg-muted/30 rounded-lg p-4">
                      <pre className="text-sm whitespace-pre-wrap font-mono leading-relaxed">
                        {result.combined_ocr_text}
                      </pre>
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
