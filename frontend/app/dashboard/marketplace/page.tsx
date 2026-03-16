"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import { isDemoMode } from "@/lib/demo-data";

interface Listing {
  id: string;
  blueprint_id: string;
  user_id: string;
  title: string;
  description: string;
  category: string;
  tags: string[];
  version: string;
  status: string;
  fork_count: number;
  rating_avg: number;
  rating_count: number;
  install_count: number;
  published_at: string;
}

const categories = ["general", "automation", "analysis", "code", "content", "data"];

async function getToken(): Promise<string> {
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token || "";
}

export default function MarketplacePage() {
  const router = useRouter();
  const [listings, setListings] = useState<Listing[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedListing, setSelectedListing] = useState<Listing | null>(null);
  const [ratings, setRatings] = useState<{ rating: number; review: string; user_id: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [forking, setForking] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (isDemoMode()) {
      setLoading(false);
      return;
    }
    loadListings();
  }, [selectedCategory]); // eslint-disable-line react-hooks/exhaustive-deps

  async function loadListings() {
    setLoading(true);
    setError("");
    try {
      const t = await getToken();
      const params: Record<string, string> = {};
      if (selectedCategory) params.category = selectedCategory;
      if (searchQuery) params.search = searchQuery;
      const qs = new URLSearchParams(params).toString();
      const data = await api.marketplace.listings(qs ? `?${qs}` : "", t);
      setListings(data);
    } catch {
      setListings([]);
      setError("Failed to load marketplace listings. Check your connection.");
    } finally {
      setLoading(false);
    }
  }

  async function handleSearch() {
    await loadListings();
  }

  async function selectListing(listing: Listing) {
    setSelectedListing(listing);
    try {
      const t = await getToken();
      if (t) {
        const r = await api.marketplace.ratings(listing.id, t);
        setRatings(r);
      }
    } catch {
      setRatings([]);
    }
  }

  function renderStars(avg: number) {
    const full = Math.floor(avg);
    const stars = [];
    for (let i = 0; i < 5; i++) {
      stars.push(
        <span key={i} className={i < full ? "text-yellow-500" : "text-muted-foreground"}>
          {i < full ? "\u2605" : "\u2606"}
        </span>
      );
    }
    return <span className="flex gap-0.5">{stars}</span>;
  }

  return (
    <div className="space-y-6">
      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Marketplace</h1>
      </div>

      {/* Search and filters */}
      <div className="flex gap-4">
        <Input
          placeholder="Search workflows..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          className="max-w-sm"
        />
        <Button onClick={handleSearch} variant="outline">Search</Button>
      </div>

      <div className="flex gap-2 flex-wrap">
        <Button
          variant={selectedCategory === "" ? "default" : "outline"}
          size="sm"
          onClick={() => setSelectedCategory("")}
        >
          All
        </Button>
        {categories.map((cat) => (
          <Button
            key={cat}
            variant={selectedCategory === cat ? "default" : "outline"}
            size="sm"
            onClick={() => setSelectedCategory(cat)}
          >
            {cat.charAt(0).toUpperCase() + cat.slice(1)}
          </Button>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Listing grid */}
        <div className="space-y-4">
          {loading ? (
            <p className="text-muted-foreground">Loading...</p>
          ) : listings.length === 0 ? (
            <p className="text-muted-foreground">No listings found.</p>
          ) : (
            listings.map((listing) => (
              <Card
                key={listing.id}
                className={`cursor-pointer transition-colors hover:bg-accent/50 ${
                  selectedListing?.id === listing.id ? "border-primary" : ""
                }`}
                onClick={() => selectListing(listing)}
              >
                <CardContent className="p-4">
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="font-semibold">{listing.title}</h3>
                      <p className="text-sm text-muted-foreground mt-1">
                        {listing.description.slice(0, 100) || "No description"}
                      </p>
                    </div>
                    <span className="rounded-full bg-accent px-2 py-0.5 text-xs">
                      {listing.category}
                    </span>
                  </div>
                  <div className="flex items-center gap-4 mt-3 text-sm text-muted-foreground">
                    <span className="flex items-center gap-1">
                      {renderStars(listing.rating_avg)}
                      <span className="ml-1">({listing.rating_count})</span>
                    </span>
                    <span>v{listing.version}</span>
                    <span>{listing.fork_count} forks</span>
                  </div>
                  {listing.tags.length > 0 && (
                    <div className="flex gap-1 mt-2 flex-wrap">
                      {listing.tags.map((tag) => (
                        <span key={tag} className="rounded bg-muted px-1.5 py-0.5 text-xs">
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            ))
          )}
        </div>

        {/* Detail panel */}
        {selectedListing && (
          <Card>
            <CardHeader>
              <CardTitle>{selectedListing.title}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm">{selectedListing.description || "No description"}</p>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <span className="text-muted-foreground">Category:</span>{" "}
                  {selectedListing.category}
                </div>
                <div>
                  <span className="text-muted-foreground">Version:</span>{" "}
                  v{selectedListing.version}
                </div>
                <div>
                  <span className="text-muted-foreground">Rating:</span>{" "}
                  {selectedListing.rating_avg.toFixed(1)} ({selectedListing.rating_count} reviews)
                </div>
                <div>
                  <span className="text-muted-foreground">Forks:</span>{" "}
                  {selectedListing.fork_count}
                </div>
              </div>

              <div className="flex gap-2">
                <Button
                  size="sm"
                  disabled={forking}
                  onClick={async () => {
                    if (!selectedListing) return;
                    setForking(true);
                    try {
                      const t = await getToken();
                      await api.marketplace.fork(selectedListing.id, { forked_blueprint_id: selectedListing.blueprint_id }, t);
                      await loadListings();
                    } catch {
                      // fork failed
                    } finally {
                      setForking(false);
                    }
                  }}
                >
                  {forking ? "Forking..." : "Fork Workflow"}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    if (!selectedListing) return;
                    router.push(`/dashboard/blueprints/${selectedListing.blueprint_id}/edit`);
                  }}
                >
                  View Blueprint
                </Button>
              </div>

              {/* Ratings */}
              <div className="border-t pt-4">
                <h4 className="font-semibold mb-2">Reviews ({ratings.length})</h4>
                {ratings.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No reviews yet.</p>
                ) : (
                  <div className="space-y-2">
                    {ratings.map((r, i) => (
                      <div key={i} className="rounded border p-2 text-sm">
                        <div className="flex items-center gap-2">
                          {renderStars(r.rating)}
                        </div>
                        {r.review && (
                          <p className="mt-1 text-muted-foreground">{r.review}</p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
