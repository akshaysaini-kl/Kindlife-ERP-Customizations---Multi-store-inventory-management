import googlemaps
import logging
import os
import frappe
from typing import Optional, Tuple, Dict
from frappe.utils import now
import hashlib

logger = logging.getLogger(__name__)

class GeocodingService:
    """
    Service for geocoding addresses to coordinates using Google Maps API
    Adapted from KindlifeLogisticServices for Frappe
    """
    
    def __init__(self):
        """Initialize Google Maps client with API key from environment or site config"""
        # Try to get API key from site config first
        api_key = frappe.get_site_config().get("google_maps_api_key")
        
        # Fall back to environment variable if not in site config
        if not api_key:
            api_key = os.getenv('GOOGLE_MAPS_API_KEY')
            
        if not api_key:
            logger.warning("Google Maps API key not found in site config or environment variables. Geocoding service will use cache only.")
            self.gmaps = None
        else:
            try:
                self.gmaps = googlemaps.Client(key=api_key)
                logger.info("Geocoding service initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Google Maps client: {e}. Geocoding service will use cache only.")
                self.gmaps = None
    
    def geocode_address(
        self, 
        shipping_address_line1: str,
        shipping_address_line2: str = None,
        shipping_city: str = None,
        shipping_state: str = None,
        shipping_pincode: str = None,
        shipping_country: str = None
    ) -> Optional[Tuple[float, float]]:
        """
        Convert full address to lat/long coordinates using Google Maps Geocoding API
        
        Args:
            address_line1: Primary address line (required)
            address_line2: Secondary address line (optional)
            city: City name (optional)
            state: State name (optional)
            pincode: Postal code (optional but recommended for accuracy)
            country: Country name (default: India)
            
        Returns:
            Tuple of (latitude, longitude) or None if geocoding fails
        """
        if not self.gmaps:
            logger.error("Google Maps client not initialized")
            return None
            
        try:
            # Build full address string
            address_parts = [shipping_address_line1]
            
            if shipping_address_line2:
                address_parts.append(shipping_address_line2)
            if shipping_city:
                address_parts.append(shipping_city)
            if shipping_state:
                address_parts.append(shipping_state)
            if shipping_pincode:
                address_parts.append(shipping_pincode)
            if shipping_country:
                address_parts.append(shipping_country)
            
            full_address = ", ".join(filter(None, address_parts))
            
            logger.info(f"Geocoding address: {full_address}")
            
            # Call Google Maps Geocoding API
            geocode_result = self.gmaps.geocode(full_address)
            
            if not geocode_result:
                logger.warning(f"No geocoding results found for address: {full_address}")
                return None
            
            # Extract coordinates from first result
            location = geocode_result[0]['geometry']['location']
            latitude = location['lat']
            longitude = location['lng']
           
            
            # Get formatted address for logging
            formatted_address = geocode_result[0].get('formatted_address', '')
            
            logger.info(
                f"Successfully geocoded to: ({latitude}, {longitude}) - "
                f"Formatted: {formatted_address}"
            )
            
            return (latitude, longitude, shipping_pincode)
            
        except googlemaps.exceptions.ApiError as e:
            logger.error(f"Google Maps API error: {e}")
            return None
        except googlemaps.exceptions.Timeout as e:
            logger.error(f"Google Maps API timeout: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected geocoding error: {e}")
            return None
    
    def geocode_address_with_cache(
        self, 
        shipping_address_line1: str,
        shipping_address_line2: str = None,
        shipping_city: str = None,
        shipping_state: str = None,
        shipping_pincode: str = None,
        shipping_country: str = None
    ) -> Optional[Dict]:
        """
        Geocode an address with caching to reduce API calls
        
        This method first checks if the address has been geocoded before,
        and only calls the Google Maps API if it's not in the cache.
        """

        try:
            # Generate address hash for cache lookup
            address_hash = self._generate_address_hash(
                shipping_address_line1, shipping_address_line2, shipping_city, shipping_state, shipping_pincode, shipping_country
            )
         
            
            # Check if we have this address in cache
            cached_addresses = frappe.get_all(
                "geocoded_addresses",  # Use lowercase to match actual doctype name
                filters={"address_hash": address_hash},
                fields=["name", "latitude", "longitude","pincode"]
            )
            
            if cached_addresses:
                # Cache HIT - return cached coordinates
                cached = cached_addresses[0]
                logger.info(f"Cache HIT for address hash {address_hash}")
                return (float(cached.latitude), float(cached.longitude), cached.pincode)
            
            # Cache MISS - Check if we can call Google API
            logger.info(f"Cache MISS for address hash {address_hash}")
            
            # If Google Maps client is not initialized, we can't geocode new addresses
            if not self.gmaps:
                logger.warning("Google Maps client not initialized - cannot geocode new address")
                frappe.msgprint("Google Maps API key not configured. Using existing geocoded addresses only.")
                return None
                
            # Call Google API since we have a client and address isn't cached
            coords = self.geocode_address(
                shipping_address_line1, shipping_address_line2, shipping_city, shipping_state, shipping_pincode, shipping_country
            )
            
            if coords:
                # Store in cache
                try:
                    doc_data = {
                        "doctype": "geocoded_addresses",  # Use lowercase to match actual doctype name
                        "address_line1": shipping_address_line1,
                        "address_line2": shipping_address_line2 or "",
                        "city": shipping_city or "",
                        "state": shipping_state or "",
                        "pincode": shipping_pincode or "",
                        "country": shipping_country or "India",
                        "address_hash": address_hash,
                        "latitude": coords[0],
                        "longitude": coords[1]
                    }
                    
                    frappe.get_doc(doc_data).insert()
                    frappe.db.commit()
                    logger.info(f"Successfully cached address with hash {address_hash}")
                except Exception as e:
                    logger.error(f"Error caching geocoding result: {e}")
                    frappe.log_error(f"Geocoding cache error: {e}", "Geocoding Service")
            
            return coords
            
        except Exception as e:
            logger.error(f"Error in geocode_address_with_cache: {e}")
            frappe.log_error(f"Geocode with cache error: {e}", "Geocoding Service")
            # Fallback to direct geocoding
            return self.geocode_address(shipping_address_line1, shipping_address_line2, shipping_city, shipping_state, shipping_pincode, shipping_country)
    
    def _generate_address_hash(
        self,
        shipping_address_line1: str,
        shipping_address_line2: str = None,
        shipping_city: str = None,
        shipping_state: str = None,
        shipping_pincode: str = None,
        shipping_country: str = None
    ) -> str:
        """Generate a hash for the address for caching"""
        address_parts = [p.lower() for p in [shipping_address_line1, shipping_address_line2, shipping_city, shipping_state, shipping_pincode, shipping_country] if p]
        address = ", ".join(address_parts)
        return hashlib.md5(address.encode()).hexdigest()
        